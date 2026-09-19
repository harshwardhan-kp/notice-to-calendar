# Build status log

Kept as a running log of what's blocked and what broke — raw material for the
writeup's "what was learned" section, not itself part of the submission.

## AWS account verification hold

This AWS account is new and under a verification hold that blocks, account-wide:

- `bedrock-runtime:InvokeModel` / `ConverseStream` — `ValidationException: Operation not allowed`
- `AWS::CloudFront::Distribution` creation — `Your account must be verified before you
  can add new CloudFront resources`

AWS's own message says this "normally clears in under 2 hours." Confirmed identical
on both a direct model ID and a cross-region inference profile, so it's not a
model-access or config problem. `template.yaml` has a `DeployCdn` parameter so the
rest of the stack (Lambda, API Gateway, S3) deploys without waiting on CloudFront;
flip it to `true` and redeploy once cleared.

## Bugs found only by testing against the real deployed stack

1. **Presigned PUT URLs 307-redirected.** `boto3.client("s3")` signs presigned URLs
   against the global `s3.amazonaws.com` host regardless of `region_name`; for any
   region other than `us-east-1` that host redirects to the real regional one.
   Fixed by passing `endpoint_url` explicitly.
2. **Presigned PUT then 403'd.** A presigned URL carries the *generating* principal's
   credentials, and S3 enforces that principal's IAM permissions when the URL is
   used, not just at generation time. The Lambda role needs `s3:PutObject` even
   though the browser is the one doing the PUT — the build spec's claim that
   PutObject "is not needed by Lambda" is wrong.
3. **HeadObject on a missing key returned 403, not 404.** Without `s3:ListBucket`
   (deliberately not granted — tightest-scope IAM), S3 masks object non-existence
   as 403 rather than 404. Handled 403 the same as 404 in that one path.
4. **Bedrock IAM needed `InvokeModelWithResponseStream`, not just `InvokeModel`.**
   Strands' `BedrockModel` streams by default (`ConverseStream`).
5. **All-day `.ics` events had the wrong `DTEND`, specifically under IST.**
   `addDays()` built a `Date` in local time then read it back with
   `toISOString()` (always UTC) — for any positive UTC offset, including IST, that
   silently subtracts a day. Fixed by doing the arithmetic in UTC throughout.

All five confirmed fixed by re-testing against the live stack (`scripts/smoketest.sh`).
The only thing still unverified end-to-end is the actual Bedrock extraction call
itself, pending the verification hold clearing.
