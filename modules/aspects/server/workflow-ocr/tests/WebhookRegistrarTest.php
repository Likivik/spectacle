<?php
declare(strict_types=1);

require_once __DIR__ . '/StubWebhookRegistrar.php';

use PHPUnit\Framework\TestCase;

final class WebhookRegistrarTest extends TestCase
{
    private const WEBHOOK_URI = 'http://127.0.0.1:8095/webhook';
    private const SECRET = 'super-secret-rotate-me-2026-10';
    private const BASE = 'https://nc.example.test';
    private const ENDPOINT = self::BASE
        . '/ocs/v2.php/apps/webhook_listeners/api/v1/webhooks';
    private const EVENT_CREATED = 'OCP\\Files\\Events\\Node\\NodeCreatedEvent';
    private const EVENT_WRITTEN = 'OCP\\Files\\Events\\Node\\NodeWrittenEvent';

    private function emptyListResponse(): array
    {
        return [200, json_encode([
            'ocs' => ['data' => []],
        ])];
    }

    private function listenerRow(
        string $event,
        int $id,
        string $secret = self::SECRET
    ): array {
        return [
            'id' => $id,
            'uri' => self::WEBHOOK_URI,
            'httpMethod' => 'POST',
            'event' => $event,
            'eventFilter' => ['event.node.path' => '/^\/.*\/files\//'],
            'userIdFilter' => '',
            'headers' => ['X-Webhook-Secret' => $secret],
            'authMethod' => 'none',
            'authData' => null,
        ];
    }

    public function testRegistersListenerViaCreateWhenNoneExists(): void
    {
        // Scripted responses, in order:
        //   1) list  -> empty
        //   2) POST create for NodeCreatedEvent -> 200
        //   3) POST create for NodeWrittenEvent -> 200
        //   4) list  -> two rows, both carrying the current secret
        $after = [
            $this->listenerRow(self::EVENT_CREATED, 11),
            $this->listenerRow(self::EVENT_WRITTEN, 12),
        ];
        $registrar = new StubWebhookRegistrar(
            self::BASE,
            'svc',
            'app-password',
            self::SECRET,
            [
                $this->emptyListResponse(),
                [200, json_encode(['ocs' => ['data' => ['id' => 11]]])],
                [200, json_encode(['ocs' => ['data' => ['id' => 12]]])],
                [200, json_encode(['ocs' => ['data' => $after]])],
            ]
        );

        $this->assertSame(0, $registrar->run());

        // Two POSTs (one per event), both to the create endpoint (no trailing id).
        $posts = $registrar->posts();
        $this->assertCount(2, $posts);
        foreach ($posts as [$method, $url, $body]) {
            $this->assertSame('POST', $method);
            $this->assertSame(self::ENDPOINT, $url);
            $this->assertIsArray($body);
            $this->assertSame(self::WEBHOOK_URI, $body['uri']);
            $this->assertSame('POST', $body['httpMethod']);
            $this->assertSame('none', $body['authMethod']);
            $this->assertNull($body['authData']);
            $this->assertSame(self::SECRET, $body['headers']['X-Webhook-Secret']);
            $this->assertContains(
                $body['event'],
                [self::EVENT_CREATED, self::EVENT_WRITTEN],
                'event class must be one of the two service events'
            );
        }
    }

    public function testReRegistrationIsIdempotentAndDoesNotDuplicate(): void
    {
        // A listener exists for both events, already carrying the current
        // secret and pointing at the right URL. run() should be a no-op:
        // list, no POSTs, list-again, exit 0.
        $existing = [
            $this->listenerRow(self::EVENT_CREATED, 21),
            $this->listenerRow(self::EVENT_WRITTEN, 22),
        ];
        $registrar = new StubWebhookRegistrar(
            self::BASE,
            'svc',
            'app-password',
            self::SECRET,
            [
                [200, json_encode(['ocs' => ['data' => $existing]])],
                [200, json_encode(['ocs' => ['data' => $existing]])],
            ]
        );

        $this->assertSame(0, $registrar->run());
        $this->assertSame(
            [],
            $registrar->posts(),
            'no POST must be issued when both listeners already match'
        );

        // The two ocsRequest calls must be GETs against the LIST (with -hi
        // uri filter).
        $this->assertCount(2, $registrar->requests);
        foreach ($registrar->requests as [$method, $url, $body]) {
            $this->assertSame('GET', $method);
            $this->assertNull($body);
            $this->assertStringStartsWith(self::ENDPOINT . '?', $url);
            $this->assertStringContainsString(
                'uri=' . rawurlencode(self::WEBHOOK_URI),
                $url
            );
        }
    }

    public function testSecretRotationIssuesAnUpdateNotADuplicateCreate(): void
    {
        // Listener exists but its stored header snapshot still carries the
        // OLD secret. run() must refresh it via PUT-style POST to the row
        // URL, not create a second listener for the same event.
        $oldSecret = 'old-secret-do-not-keep';
        $existing = [
            $this->listenerRow(self::EVENT_CREATED, 31, $oldSecret),
            $this->listenerRow(self::EVENT_WRITTEN, 32, self::SECRET),
        ];
        $after = [
            $this->listenerRow(self::EVENT_CREATED, 31, self::SECRET),
            $this->listenerRow(self::EVENT_WRITTEN, 32, self::SECRET),
        ];
        $registrar = new StubWebhookRegistrar(
            self::BASE,
            'svc',
            'app-password',
            self::SECRET,
            [
                [200, json_encode(['ocs' => ['data' => $existing]])],
                [200, json_encode(['ocs' => ['data' => ['id' => 31]]])],
                [200, json_encode(['ocs' => ['data' => $after]])],
            ]
        );

        $this->assertSame(0, $registrar->run());

        // One POST, addressed to /{id} (the update endpoint), carrying the
        // NEW secret in the header.
        $posts = $registrar->posts();
        $this->assertCount(1, $posts);
        [$method, $url, $body] = $posts[0];
        $this->assertSame('POST', $method);
        $this->assertSame(self::ENDPOINT . '/31', $url);
        $this->assertSame(self::SECRET, $body['headers']['X-Webhook-Secret']);
        $this->assertSame(self::EVENT_CREATED, $body['event']);
    }

    public function testNonTwoXxOcsResponseSurfacesAsError(): void
    {
        // Create returns 500. run() must surface that as a failure: exit
        // code 1 (verify reports errors). Critically NOT 0 - that is the
        // contract the script's comment makes explicit ("0 only when BOTH
        // listeners are confirmed to carry the current webhook secret").
        $registrar = new StubWebhookRegistrar(
            self::BASE,
            'svc',
            'app-password',
            self::SECRET,
            [
                $this->emptyListResponse(),
                [500, 'internal server error'],
                // Verification list still sees the rows, but the failed one
                // carries the placeholder secret "" (no headers set), so
                // verify() catches it.
                [200, json_encode(['ocs' => ['data' => [
                    $this->listenerRow(self::EVENT_CREATED, 41, ''),
                    $this->listenerRow(self::EVENT_WRITTEN, 42, self::SECRET),
                ]]])],
            ]
        );

        $this->assertSame(
            1,
            $registrar->run(),
            'a 500 from create must propagate as a non-zero exit, not success'
        );

        // HTTP calls in order: list (1), POST create NodeCreatedEvent (2 -
        // 500), POST create NodeWrittenEvent (3 - 200), list again (4).
        // The script's apply() keeps going after a failure, so the second
        // event is still created; then verify() re-reads and catches that the
        // bad row still does not carry the current secret.
        $this->assertCount(4, $registrar->requests);
        $this->assertSame('GET', $registrar->requests[0][0]);
        $this->assertSame('POST', $registrar->requests[1][0]);
        $this->assertSame(self::ENDPOINT, $registrar->requests[1][1]);
        $this->assertSame(self::EVENT_CREATED, $registrar->requests[1][2]['event']);
        $this->assertSame('POST', $registrar->requests[2][0]);
        $this->assertSame(self::EVENT_WRITTEN, $registrar->requests[2][2]['event']);
        $this->assertSame('GET', $registrar->requests[3][0]);
    }

    public function testListFailureShortCircuitsAndReturnsOne(): void
    {
        // Even before any create/update, a non-2xx on the initial list
        // must abort with exit 1 and produce no POSTs.
        $registrar = new StubWebhookRegistrar(
            self::BASE,
            'svc',
            'app-password',
            self::SECRET,
            [
                [401, 'unauthorised'],
            ]
        );

        $this->assertSame(1, $registrar->run());
        $this->assertSame([], $registrar->posts());
        $this->assertCount(1, $registrar->requests);
    }
}