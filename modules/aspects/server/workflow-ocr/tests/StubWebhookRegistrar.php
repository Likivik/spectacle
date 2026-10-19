<?php
declare(strict_types=1);

if (!defined('WORKFLOW_OCR_TEST_MODE')) {
    define('WORKFLOW_OCR_TEST_MODE', 1);
}

// Wrap the production script in a try/catch so the trailing top-level
// `WebhookRegistrar::fromArgv($argv)` (which calls @file_get_contents('') when
// $argv is missing the password-file argument) cannot abort PHPUnit. In
// production $argv is the real CLI argv and the file path is non-empty, so this
// try is dead code outside tests.
try {
    require_once dirname(__DIR__) . '/register-webhook.php';
} catch (\ValueError $e) {
    // Production code path triggered under test conditions: WORKFLOW_OCR_TEST_MODE
    // is set, the trailing code is a no-op already.
}

/**
 * Test double for WebhookRegistrar that captures every ocsRequest() call and
 * replays a scripted sequence of [code, body] responses.
 *
 * The production class leaves ocsRequest() protected specifically for tests;
 * no live Nextcloud is needed. Requests are kept in the order they were made
 * so a test can assert on the sequence (list, then create/update, then
 * verify-list).
 */
final class StubWebhookRegistrar extends WebhookRegistrar
{
    /** @var list<array{0:string,1:string,2:?array<string,mixed>}> */
    public array $requests = [];

    /** @var list<array{0:int,1:string}> */
    private array $responses;

    private int $idx = -1;

    /**
     * @param list<array{0:int,1:string}> $responses
     *   HTTP status + raw body for each ocsRequest() call, in order. The last
     *   entry is repeated for any extra calls so a test does not need to
     *   count exactly.
     */
    public function __construct(
        string $baseUrl,
        string $serviceUser,
        string $appPassword,
        string $webhookSecret,
        array $responses
    ) {
        parent::__construct($baseUrl, $serviceUser, $appPassword, $webhookSecret);
        $this->responses = $responses;
    }

    protected function ocsRequest(
        string $method,
        string $url,
        ?array $body = null
    ): array {
        $this->requests[] = [$method, $url, $body];
        if ($this->idx + 1 >= count($this->responses)) {
            $this->idx = count($this->responses) - 1;
        } else {
            $this->idx++;
        }
        return $this->responses[$this->idx];
    }

    /**
     * @return list<array{0:string,1:string,2:?array<string,mixed>}>
     */
    public function posts(): array
    {
        return array_values(array_filter(
            $this->requests,
            static fn(array $r): bool => $r[0] === 'POST'
        ));
    }
}