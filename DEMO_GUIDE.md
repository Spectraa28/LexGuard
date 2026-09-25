# LexGuard demo guide

For a concise recorded walkthrough, use [`VIDEO_DEMO_SCRIPT.md`](VIDEO_DEMO_SCRIPT.md).

## Start the demo

1. Add the Cloudflare R2 values documented in `README.md` to `.env`.
2. Prepare two small, text-based PDF contracts. Scanned PDFs require an OCR worker.
3. Start and wait for the stack:

   ```bash
   ./scripts/demo.sh start
   ```

4. Open `http://localhost:8088`.
5. Upload one PDF before presenting and wait for **Completed**. Keep the other for the live upload.
6. Run one search before presenting to warm the embedding model.

## Suggested live flow

1. **Overview:** introduce real document, service, queue, vector, and recovery state.
2. **Documents:** upload a PDF and explain durable asynchronous checkpoints.
3. **Search:** retrieve page-level evidence from the prepared document.
4. **System tests:** run tenant isolation and supervisor recovery checks.
5. **Architecture:** explain the ingestion, retrieval, and recovery paths.

## Commands

```bash
./scripts/demo.sh start   # build, start, and wait for readiness
./scripts/demo.sh status  # show containers and URLs
./scripts/demo.sh logs    # follow application logs
./scripts/demo.sh stop    # stop while preserving volumes
```

The first worker startup can take longer while its embedding model is populated in the persistent `model_cache` volume.
