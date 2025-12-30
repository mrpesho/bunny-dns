# Bunny.net DNS & Pull Zone Auto-Setup

A Python CLI tool for declaratively managing DNS zones, Pull Zones, and Edge Rules on [bunny.net](https://bunny.net) from a JSON configuration file.

## Features

- **Declarative configuration** - Define your desired state in JSON, the tool syncs it to bunny.net
- **DNS management** - Create zones, manage A, AAAA, CNAME, TXT, MX, SRV, and other record types
- **Pull Zone management** - Create CDN pull zones with custom origins and regional pricing
- **Hostname & SSL** - Automatically add custom hostnames and provision free SSL certificates
- **Edge Rules** - Configure CDN edge rules with friendly action/trigger names
- **Dry-run mode** - Preview changes before applying
- **Domain isolation** - Sync specific domains without affecting others

## Installation

```bash
# Clone the repository
git clone https://github.com/mrpesho/autoset_bunny_dns.git
cd autoset_bunny_dns

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
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

```bash
# Sync a specific domain (recommended)
python main.py -c config.json --domain example.com

# Dry run - preview changes without applying
python main.py -c config.json --domain example.com --dry-run

# DNS only
python main.py -c config.json --domain example.com --dns-only

# Pull zones only
python main.py -c config.json --domain example.com --pullzones-only

# Additive mode - don't delete records not in config
python main.py -c config.json --domain example.com --no-delete

# Sync all domains in config
python main.py -c config.json
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-c, --config` | Path to JSON configuration file (required) |
| `-d, --domain` | Only sync this specific domain |
| `-n, --dry-run` | Preview changes without applying |
| `--dns-only` | Only sync DNS zones |
| `--pullzones-only` | Only sync Pull Zones |
| `--no-delete` | Don't delete records not in config |
| `--api-key` | API key (defaults to `BUNNY_API_KEY` env var) |

## Check Propagation Status

After updating nameservers, check if DNS has propagated:

```bash
# Basic check
python check_propagation.py example.com

# Include pull zone hostname/SSL checks
python check_propagation.py example.com -c config.json
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
2. **Run with dry-run** to verify: `python main.py -c config.json --domain example.com --dry-run`
3. **Apply changes**: `python main.py -c config.json --domain example.com`
4. **Update nameservers** at your registrar to bunny.net's nameservers
5. **Re-run sync** to load SSL certificates (requires DNS propagation)

Bunny.net nameservers:
- `kiki.bunny.net`
- `coco.bunny.net`

## Safety Features

- **Domain isolation** - Only touches domains explicitly in your config
- **Dry-run mode** - Preview all changes before applying
- **No-delete mode** - Additive only, never removes records
- **Rate limit handling** - Auto-retry with exponential backoff
- **Explicit domain flag** - `--domain` ensures you only sync what you intend

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
