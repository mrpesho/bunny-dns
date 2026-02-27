# Bunny.net DNS & Pull Zone Auto-Setup

A Python CLI tool for declaratively managing DNS zones, Pull Zones, and Edge Rules on [bunny.net](https://bunny.net) from a JSON configuration file.

## Features

- **Declarative configuration** - Define your desired state in JSON, the tool syncs it to bunny.net
- **DNS management** - Create zones, manage A, AAAA, CNAME, TXT, MX, SRV, and other record types
- **Pull Zone management** - Create CDN pull zones with custom origins and regional pricing
- **Hostname & SSL** - Automatically add custom hostnames and provision free SSL certificates
- **Edge Rules** - Configure CDN edge rules with friendly action/trigger names
- **Pull from bunny.net** - Export existing infrastructure as a config JSON (`--sot bunny`)
- **Dry-run mode** - Preview changes before applying
- **Domain isolation** - Sync specific domains without affecting others

## Installation

```bash
pip install bunny-dns
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install bunny-dns
```

For development:

```bash
git clone https://github.com/mrpesho/bunny-dns.git
cd bunny-dns
pip install -e ".[dev]"
```

## Configuration

1. Copy the example files:
```bash
cp .env.example .env
cp config.example.json config.json
```

2. Add your bunny.net API key to `.env`:
```
BUNNY_API_KEY=your-api-key-here
```

3. Edit `config.json` with your domains and records.

### Configuration Format

```json
{
  "domains": {
    "example.com": {
      "dns_records": [
        {"type": "A", "name": "@", "value": "1.2.3.4", "ttl": 3600},
        {"type": "AAAA", "name": "@", "value": "2606:50c0:8000::153", "ttl": 3600},
        {"type": "CNAME", "name": "www", "value": "example.com", "ttl": 3600},
        {"type": "MX", "name": "@", "value": "mail.example.com", "priority": 10, "ttl": 3600},
        {"type": "TXT", "name": "@", "value": "v=spf1 include:_spf.google.com ~all", "ttl": 3600},
        {"type": "SRV", "name": "_sip._tcp", "value": "sip.example.com", "priority": 10, "weight": 60, "port": 5060, "ttl": 3600}
      ],
      "pull_zones": {
        "my-cdn": {
          "origin_url": "https://origin.example.com",
          "origin_host_header": "origin.example.com",
          "type": "standard",
          "enabled_regions": ["EU", "US"],
          "hostnames": ["cdn.example.com"],
          "edge_rules": []
        }
      }
    }
  }
}
```

### Supported DNS Record Types

| Type | Description |
|------|-------------|
| A | IPv4 address |
| AAAA | IPv6 address |
| CNAME | Canonical name |
| TXT | Text record |
| MX | Mail exchange (requires `priority`) |
| SRV | Service record (requires `priority`, `weight`, `port`) |
| CAA | Certificate Authority Authorization |
| NS | Name server |
| PTR | Pointer record |

### Pull Zone Options

| Option | Description |
|--------|-------------|
| `origin_url` | Origin server URL |
| `origin_host_header` | Host header sent to origin |
| `type` | `standard` or `volume` |
| `enabled_regions` | Array of: `EU`, `US`, `ASIA`, `SA`, `AF` |
| `hostnames` | Custom hostnames (SSL auto-provisioned) |
| `edge_rules` | Array of edge rule configurations |

### Edge Rules

```json
{
  "edge_rules": [
    {
      "description": "CORS Headers",
      "enabled": true,
      "trigger_match": "any",
      "triggers": [
        {"type": "url", "match": "any", "patterns": ["*"]}
      ],
      "actions": [
        {"type": "set_response_header", "header": "Access-Control-Allow-Origin", "value": "*"}
      ]
    }
  ]
}
```

**Trigger types:** `url`, `url_extension`, `url_query_string`, `request_header`, `response_header`, `country_code`, `remote_ip`, `status_code`, `request_method`, `random_chance`

**Action types:** `set_response_header`, `set_request_header`, `redirect`, `block`, `force_ssl`, `override_cache_time`, `origin_url`, `force_download`, `disable_optimizer`, `set_status_code`

## Usage

> **Note:** If you installed with `uv`, prefix commands with `uv run` (e.g. `uv run bunny-dns ...`).

### Push (local → bunny.net)

```bash
# Sync a specific domain (recommended)
bunny-dns -c config.json --domain example.com

# Dry run - preview changes without applying
bunny-dns -c config.json --domain example.com --dry-run

# DNS only
bunny-dns -c config.json --domain example.com --dns-only

# Pull zones only
bunny-dns -c config.json --domain example.com --pullzones-only

# Additive mode - don't delete records not in config
bunny-dns -c config.json --domain example.com --no-delete

# Sync all domains in config
bunny-dns -c config.json
```

### Pull (bunny.net → local)

Export your current bunny.net configuration as JSON — useful for bootstrapping a config from existing infrastructure or verifying drift.

```bash
# Pull a specific domain
bunny-dns --sot bunny --domain example.com

# Pull all DNS zones on the account
bunny-dns --sot bunny --all

# Write to file instead of stdout
bunny-dns --sot bunny --domain example.com -o config.json

# Pull DNS only or pull zones only
bunny-dns --sot bunny --domain example.com --dns-only
bunny-dns --sot bunny --domain example.com --pullzones-only
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-c, --config` | Path to JSON configuration file (required for push) |
| `-d, --domain` | Only sync/pull this specific domain |
| `-n, --dry-run` | Preview changes without applying (push only) |
| `--dns-only` | Only sync/pull DNS zones |
| `--pullzones-only` | Only sync/pull Pull Zones |
| `--no-delete` | Don't delete records not in config (push only) |
| `--sot` | Source of truth: `local` (default, push) or `bunny` (pull) |
| `--all` | Pull all DNS zones on the account (with `--sot bunny`) |
| `-o, --output` | Write pull output to file instead of stdout |
| `--api-key` | API key (defaults to `BUNNY_API_KEY` env var) |

## Check Propagation Status

After updating nameservers, check if DNS has propagated:

```bash
# Basic check
bunny-dns-check example.com

# Include pull zone hostname/SSL checks
bunny-dns-check example.com -c config.json
```

Output:
```
NAMESERVERS: ✓ OK
  Expected: coco.bunny.net, kiki.bunny.net
  Current:  kiki.bunny.net, coco.bunny.net
  → DNS is pointing to bunny.net

DNS RECORDS:
  ✓ A        @                    → 185.199.110.153, 185.199.111.153
  ✓ AAAA     @                    → 2606:50c0:8000::153, 2606:50c0:8003::153
  ✓ MX       @                    → 0 mail.example.com

PULL ZONE HOSTNAMES:
  ✓ cdn.example.com
      CNAME: my-cdn.b-cdn.net
      SSL:   ok (200)
```

## Workflow: Migrating to Bunny DNS

1. **Create config** with your current DNS records
2. **Run with dry-run** to verify: `bunny-dns -c config.json --domain example.com --dry-run`
3. **Apply changes**: `bunny-dns -c config.json --domain example.com`
   - Pull zone hostnames are added, but SSL certificates will fail (DNS not pointing to bunny yet)
4. **Update nameservers** at your registrar to [bunny.net's nameservers](https://docs.bunny.net/docs/dns-getting-started):
   - `kiki.bunny.net`
   - `coco.bunny.net`
5. **Check propagation**: `bunny-dns-check example.com -c config.json`
6. **Re-run sync** to load SSL certificates: `bunny-dns -c config.json --domain example.com`
   - The script automatically detects hostnames missing certificates and loads them

## Safety Features

- **Domain isolation** - Only touches domains explicitly in your config
- **Dry-run mode** - Preview all changes before applying
- **No-delete mode** - Additive only, never removes records
- **Rate limit handling** - Auto-retry with exponential backoff
- **Explicit domain flag** - `--domain` ensures you only sync what you intend

## Testing

The project includes a comprehensive test suite with 99% code coverage.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=bunny_dns --cov-report=term-missing

# Run specific test file
pytest tests/test_dns_manager.py -v
```

### Test Structure

| File | Tests | Coverage |
|------|-------|----------|
| `test_bunny_client.py` | HTTP client, retries, exceptions | 100% |
| `test_dns_manager.py` | DNS records, normalization, sync | 100% |
| `test_pullzone_manager.py` | Pull zones, hostnames, regions | 99% |
| `test_edge_rules_manager.py` | Edge rules, action/trigger parsing | 100% |
| `test_sync.py` | Orchestrator, config loading | 99% |

## Use Case: Fathom Analytics Proxy

A common use case is proxying [Fathom Analytics](https://usefathom.com) through Bunny CDN to bypass ad blockers:

```json
{
  "domains": {
    "example.com": {
      "dns_records": [
        {"type": "CNAME", "name": "fa", "value": "fa-example.b-cdn.net", "ttl": 3600}
      ],
      "pull_zones": {
        "fa-example": {
          "origin_url": "https://cdn.usefathom.com",
          "origin_host_header": "cdn.usefathom.com",
          "type": "standard",
          "enabled_regions": ["EU", "US"],
          "hostnames": ["fa.example.com"],
          "edge_rules": []
        }
      }
    }
  }
}
```

Then use `fa.example.com` as your Fathom custom domain.

## License

MIT

---

## Support

If you're new to bunny.net and find this tool useful, consider signing up through my [affiliate link](https://bunny.net?ref=cklqznj7qp). It helps support continued development at no extra cost to you.
