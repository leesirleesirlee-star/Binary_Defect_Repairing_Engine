# Static console shell (S1)

Install the shell-only runtime dependencies (M1 owns the root requirements file):

```bash
pip install 'fastapi>=0.115,<1' 'uvicorn>=0.30,<1'
```

Run the copied v1.2.2 welcome/chat/archive surfaces unchanged:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8124
```

- <http://127.0.0.1:8124/welcome>
- <http://127.0.0.1:8124/ui/chat/?preview=1>
- <http://127.0.0.1:8124/ui/>

S2 guided intake is included: `/api/fixture` exposes the frozen G1 fixture,
contract and corpus; the chat hero opens a read-only intake/approval dialog. The
S3-S6 API, SSE journal, audit/repair/verify payloads and Start action are not
part of this slice; the GUI still never computes a verdict and Start stays
disabled until the S3 runner exists.
