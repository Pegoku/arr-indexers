# arr-indexers

Torznab proxy services for Prowlarr-compatible indexers that need runtime logic beyond a normal Cardigann YAML definition.

The first included service is DonTorrent, exposed as a Generic Torznab indexer for Prowlarr.

## Why This Exists

Some indexers do not expose static torrent links. DonTorrent currently requires a proof-of-work challenge before returning the final `.torrent` URL, which cannot be represented cleanly as a standard Prowlarr Cardigann YAML definition.

This project runs those indexer-specific flows behind a Torznab-compatible HTTP API.

## Run With Docker

```bash
docker run --rm \
  -p 9697:9697 \
  ghcr.io/pegoku/arr-indexers:latest
```

## Run Locally

```bash
python3 -m arr_indexers --host 0.0.0.0 --port 9697
```

## Prowlarr Setup

Add a new `Generic Torznab` indexer:

- Name: `DonTorrent`
- URL: `http://127.0.0.1:9697/api`
- API key: any value, unless `ARR_INDEXERS_API_KEY` is set

If Prowlarr runs in Docker, use an address reachable from the Prowlarr container, such as `http://host.docker.internal:9697/api` where supported, or the host LAN IP.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `ARR_INDEXERS_HOST` | `0.0.0.0` in Docker, `127.0.0.1` locally | Bind address |
| `ARR_INDEXERS_PORT` | `9697` | HTTP port |
| `ARR_INDEXERS_API_KEY` | unset | Optional Torznab API key check |
| `ARR_INDEXERS_LOG_LEVEL` | `INFO` | Python log level |
| `DONTORENT_BASE_URL` | `auto` | DonTorrent proxy URL. Use `auto` to resolve it from DonProxies. |
| `DONTORENT_PROXY_SOURCE_URL` | `https://donproxies.com/` | DonProxies page used for auto-discovery |

DonTorrent proxy domains rotate. By default the service reads https://donproxies.com/ and uses the current generated proxy. Set `DONTORENT_BASE_URL` only if you want to pin a specific proxy URL.

## Endpoints

- `GET /health`
- `GET /api?t=caps`
- `GET /api?t=search&q=iron%20man%202`
- `GET /api?t=movie&q=iron%20man%202`
- `GET /api?t=tvsearch&q=oasis`

## Image Publishing

The GitHub Actions workflow builds the Docker image on pull requests and publishes it to GHCR on pushes to `main` and version tags.

No registry secrets are required. The workflow uses the repository `GITHUB_TOKEN` with `packages: write`.

Published image:

```text
ghcr.io/pegoku/arr-indexers:latest
```
