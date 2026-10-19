# NC webhook delivery retry — verdict + evidence

> Question: if the OCR service is down when NC dispatches a file event, will NC
> retry, or does the client need a catch-up scan?
>
> **Verdict: PARTIAL.** NC enqueues the dispatch as a *background job* that is
> retried, but: (1) the retry happens on the default cron schedule (≤5 min),
> not as exponential backoff inside the same request; (2) Nextcloud **does
> NOT retry an *exception*** thrown out of `WebhookCall::start()` more than
> once, because `WebhookCall` is a `QueuedJob` (run-once-and-delete); (3) any
> **non-2xx response is logged at WARNING and silently dropped** — the job row
> is deleted on the way out, so a 401/500/timeout does not get a second chance
> either; and (4) when the WebhookCall job itself crashes mid-run, the row
> gets its `last_checked` pushed *12 hours into the future* by JobList before
> the row is re-tried, so a restarted/dispatching race can hide a missed file
> for that long. Reliable delivery therefore requires **client-side
> reconciliation** — a periodic scan that picks up anything whose upload
> predates a service-window.

---

## 1. Which component dispatches events registered against `OCP\WorkflowEngine\IEntityCheck` hooks?

We are not actually using the workflowengine app here — `modules/aspects/server/workflow-ocr/register-webhook.php` registers via the `webhook_listeners` OCS API:

```
$this->endpoint = $baseUrl . '/ocs/v2.php/apps/webhook_listeners/api/v1/webhooks';
```
(`register-webhook.php:80`)

So the dispatch path is `apps/webhook_listeners`, not `apps/workflowengine`. The dispatch itself is **asynchronous, mediated by the background-job system**:

1. `WebhooksEventListener::handle()` runs synchronously in the request that fired
   the event (it is an `OCP\EventDispatcher\IEventListener`). For every matched
   webhook it calls `$this->jobList->add(WebhookCall::class, [...])`.

   ```php
   // apps/webhook_listeners/lib/Listener/WebhooksEventListener.php
   $this->jobList->add(
       WebhookCall::class,
       [ $data, $webhookListener->getId(), bin2hex(random_bytes(5)) ]
   );
   ```
   Source: <https://github.com/nextcloud/server/blob/master/apps/webhook_listeners/lib/Listener/WebhooksEventListener.php>

2. `WebhookCall` is a `QueuedJob` (run-once). Cron / `occ background-job:worker`
   picks it up later, calls `$client->request(...)`, and the job is deleted on
   the way out (see §2).

   ```php
   // apps/webhook_listeners/lib/BackgroundJobs/WebhookCall.php
   $response = $client->request($webhookListener->getHttpMethod(), $webhookUri, $options);
   $statusCode = $response->getStatusCode();
   if ($statusCode >= 200 && $statusCode < 300) { ... }
   else { $this->logger->warning('Webhook('.$webhookId.') returned unexpected status code '.$statusCode, ...); }
   ```
   Source: <https://raw.githubusercontent.com/nextcloud/server/master/apps/webhook_listeners/lib/BackgroundJobs/WebhookCall.php>

So: dispatch is **NOT** synchronous in the request path — it is handed off to
the background job system. (Both the older `webhooks` app, replaced 2024-06 by
`webhook_listeners`, and the unrelated `flow_webhooks` archive use the same
`WebhookCall::class` queue. Old `kffl/nextcloud-webhooks` does its own
fire-and-forget curl exec, but is *not* what register-webhook.php uses.)

## 2. Does NC retry a failed delivery? Backoff? Dead-letter?

Not in any meaningful sense for *our* case. Three layers of behaviour:

### 2a. Application layer (what `WebhookCall` actually does)

- It does **not** throw on a non-2xx response. It just logs a warning and returns.

  ```php
  } else {
      $this->logger->warning('Webhook('.$webhookId.') returned unexpected status code '.$statusCode, ...);
  }
  ```
  Status `200 ≤ s < 300` is treated as success; anything else is logged and dropped.
  (<https://raw.githubusercontent.com/nextcloud/server/master/apps/webhook_listeners/lib/BackgroundJobs/WebhookCall.php>)

- It also logs `error` for an exception but never re-queues.

  ```php
  } catch (\Exception $e) {
      $this->logger->error('Webhook('.$webhookId.') call failed: '.$e->getMessage(), ...);
  }
  ```

- `WebhookCall` is a `QueuedJob`. Its `start()` removes the row before/after
  it runs:

  ```php
  // lib/public/BackgroundJob/QueuedJob.php
  final public function start(IJobList $jobList): void {
      if ($this->id) { $jobList->removeById($this->id); }
      else { $jobList->remove($this, $this->argument); }
      parent::start($jobList);
  }
  ```
  (<https://raw.githubusercontent.com/nextcloud/server/master/lib/public/BackgroundJob/QueuedJob.php>)

  i.e. "run once and discard — no retry, no backoff, no dead-letter".

### 2b. Background-job system (generic NC retry on exception)

`Job::start()` (`lib/private/BackgroundJob/Job.php`) *catches* any
`\Throwable` from `run()`:

```php
try {
    $this->run($this->argument);
    ...
} catch (\Throwable $e) {
    $logger->error('Error while running background job '.$jobDetails, ...);
}
```
(<https://github.com/nextcloud/server/blob/master/lib/private/BackgroundJob/Job.php>)

So if `WebhookCall::start()` does propagate an exception out of `run()` (e.g.
connection refused, DNS failure, TLS verification fail, json_encode size blow-up),
the job row stays in the table — but with `last_checked = now + 12h`:

```php
// JobList::getNext() — when buildJob returned null OR the row was unprocessable:
$reset = $this->connection->getQueryBuilder();
$reset->update('jobs')
    ->set('reserved_at', $reset->expr()->literal(0, IQueryBuilder::PARAM_INT))
    ->set('last_checked', $reset->createNamedParameter($this->timeFactory->getTime() + 12 * 3600, IQueryBuilder::PARAM_INT))
    ->where($reset->expr()->eq('id', $reset->createNamedParameter($row['id'], IQueryBuilder::PARAM_INT)));
$reset->executeStatement();
```
(<https://raw.githubusercontent.com/nextcloud/server/master/lib/private/BackgroundJob/JobList.php>)
"Background job from disabled app, try again." → actually any job that
crashes during dispatch gets this 12-hour shadow.

The job stays in the table, but it will not be picked up for ~12 hours. There
is **no exponential backoff, no attempt counter, no DLQ** — a single row
sitting around forever.

The select query that decides what's runnable:

```php
->where($query->expr()->lte('reserved_at', $query->createNamedParameter(... time() - 12 * 3600 ...)))
->andWhere($query->expr()->lte('last_checked', $query->createNamedParameter(... time() ...)))
```
(`getNext`, same file)

### 2c. Crash-during-run penalty (the exact "service was restarting" case)

marcelklehr explained this in practice on `recognize` discussion #821:
"When a background job is killed while running it will not be executed for a
minimum of 12h. ... set the last_checked to 12h in the future to not check
failing jobs all over again." — and confirmed at
`server/lib/private/BackgroundJob/JobList.php`.
(<https://github.com/nextcloud/recognize/discussions/821>)

So:

- **Service is briefly restarting → curl throws `connect refused` →
  `WebhookCall::run()` throws → `Job::start()` catches it → row gets
  `last_checked = now + 12*3600`.** The next 12 hours of cron runs ignore the
  file's event; if cron expires the row before another event arrives the file
  is never OCR'd.
- **Service returns 5xx, 401, or any non-2xx → `WebhookCall` logs a warning and
  returns normally → `Job::start()` sees no exception → row is deleted on the
  way out. No retry.**
- **Service is *down* at dispatch time but recovers within 5 min (cron
  resolution) → the next cron tick fires the call → no retry needed.** This
  is the only path where Nextcloud's behaviour actually agrees with intuition.

## 3. Can an operator fix this with config alone?

**No.** Per the evidence above:

- `webhook_listeners` registers a `QueuedJob`, which by definition is
  run-once-and-discard. There is no `maxRetries`, no `backoff`, no DLQ knob
  in the app. It uses Nextcloud's standard job-list machinery, not a custom
  retry queue like `RetryJob` (`apps/federatedfilesharing/lib/BackgroundJob/RetryJob.php`)
  where `maxTry = 20` and `interval = 600` are explicitly checked in
  `shouldRun()`. (`RetryJob` is a `Job`, not a `QueuedJob`, *because* it
  reschedules itself.)

- You can only improve *freshness* of the FIRST pickup, not retry on
  failure: the admin manual documents `occ background-job:worker -t 60
  'OCA\WebhookListeners\BackgroundJobs\WebhookCall'` as the way to keep
  dispatch latency close to zero *for jobs that succeeded*. A worker just
  shifts when the first attempt happens.
  (<https://docs.nextcloud.com/server/stable/admin_manual/webhook_listeners/index.html#speeding-up-webhook-dispatch>)

- You can restart the *job row* by `occ background-job:execute <id>` or run
  `occ background-job:delete` and re-add the webhook — i.e. operator
  babysitting, not an automated retry.

So `webhook_listeners` is **fire-and-forget with no application-level
reliability**. Reliable delivery needs **client-side reconciliation**: a
periodic scan of files in the user's tree that were created after the OCR
service's last healthy ACK and that do not yet carry the OCR result
metadata. (This is exactly why `pkgs/nc-ocr-flow/src/nc_ocr_flow/webhook_server.py`
exposes `/scan-all`, `/rescan`, `/reconcile`, and `/admin/reconcile-orphans`,
and why the comment block at the top of `_enqueue()` emphasises "durable
queue insert".)

## 4. What HTTP status / timeout does NC treat as success vs failure?

From `apps/webhook_listeners/lib/BackgroundJobs/WebhookCall.php`:

- **Success** = `200 ≤ status < 300`. Body is logged at `debug`, no exception.
- **Any 3xx/4xx/5xx** = logged at `warning`, treated as a finished delivery.
  **No retry.** (No `302` follow handling; whatever `IClientService` returns
  is what the world sees.)
- **Network/DNS/TLS/JSON-encoding/4000-char-argument failure** = `\Exception`
  caught at the top of the try, logged at `error`, job row survives but with
  `last_checked = now + 12h`. No retry before the 12h window.
- **No request timeout is configured in the app.** The default
  `OC\Http\Client\Client` is used; the only options NC sets are `verify`
  (CA bundle), `headers` (auth header), and `body` (JSON payload). No
  `timeout` / `connect_timeout`. If the listener accepts the connection but
  then never responds, the cron worker is held for as long as the OS / PHP-FPM
  default cURL timeout — typically tens of seconds to a few minutes, blocking
  one cron slot per occupied worker.

The webhook POST that our own `/webhook` handler receives returns:

- **400** for malformed JSON body (so a 400 here stops NC from retry-storming,
  because the warning branch in `WebhookCall` never re-queues regardless of
  status — see `pkgs/nc-ocr-flow/src/nc_ocr_flow/webhook_server.py:2587`).
- **401** for bad/secret-missing headers.
- **413** for bodies > 2 MiB (`webhook_server.py:2564`).
- **503** for "webhook secret is not configured" (`webhook_server.py:2537`).
- **200** for everything else (ignored path / queued / foreign-user /
  recently-processed), so NC sees the file as "handled" and stops trying.

Given that `WebhookCall` drops the row on any non-2xx, our listener's *own*
behaviour here already covers the "NC retries 5xx indefinitely" worry — but
it does so by *logging the file as a failed delivery with no chance of
retry*. Hence the client-side reconciliation the panel/build exposes.

---

## Concrete recommendation

**Client-side catch-up scan IS required.** Treat NC's `webhook_listeners`
as best-effort fire-and-forget. Two safety nets in particular:

1. **Run `nc-ocr-flow`'s `/reconcile` periodically** (it walks the user's
   file tree and queues anything the index doesn't have an OCR result for),
   and/or wire `cron-jobber` to `/scan-all` on a low cadence (e.g. nightly).
2. **Treat 401/500 from our `/webhook`** as a signal to re-publish the
   webhook registration — not to expect NC to retry. (The
   `register-webhook.php` exit-0-on-both-listeners-secret-verified gate
   already covers secret-rotations.)

Config-only mitigations that *do* help:

- Run dedicated `background-job:worker` for `WebhookCall` to lower the
  latency of the *first* attempt (but they do nothing about retries).
- Keep the OCR service UP so a connection-refused never happens and the
  `WebhookCall` job always sees a 200.

What does NOT help:

- Increasing any retry count: `webhook_listeners` has none to tune.
- Lowering system load: unrelated to delivery guarantees.
