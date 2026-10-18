#!/usr/bin/env bash
# Read-only health check for the server that will run the bot.
# It changes nothing and never prints secret values (only whether each .env key is filled).
#
#   bash scripts/check-server.sh            # from the repo folder
#   bash scripts/check-server.sh bot.example.com

DOMAIN_ARG="$1"
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
section() { printf '\n== %s ==\n' "$*"; }

section "System"
. /etc/os-release 2>/dev/null && ok "OS: ${PRETTY_NAME:-unknown}" || warn "OS: unknown"
ok "Kernel: $(uname -r)   Arch: $(uname -m)"
ok "CPU cores: $(nproc 2>/dev/null)"
free -h 2>/dev/null | awk '/Mem:/ {print "  ✔ RAM: total " $2 ", available " $7}'
df -h / 2>/dev/null | awk 'NR==2 {print "  ✔ Disk /: size " $2 ", free " $4 " (" $5 " used)"}'
[ "$(id -u)" = 0 ] && ok "Running as root" || warn "Not root (you may need sudo for docker)"

section "Location"
PUBIP=$(curl -s -m 8 https://api.ipify.org)
COUNTRY=$(curl -s -m 8 "https://ipinfo.io/${PUBIP}/country" | tr -d '[:space:]')
[ -n "$PUBIP" ] && ok "Public IP: $PUBIP" || bad "Could not detect public IP"
if [ "$COUNTRY" = "IR" ]; then bad "Country: IR - Telegram and Claude APIs are not reachable from Iran"
elif [ -n "$COUNTRY" ]; then ok "Country: $COUNTRY"; else warn "Country: unknown"; fi

section "Docker"
if command -v docker >/dev/null; then
  ok "$(docker --version)"
  docker compose version >/dev/null 2>&1 && ok "$(docker compose version)" || bad "docker compose plugin missing"
  docker info >/dev/null 2>&1 && ok "Docker daemon is running" || bad "Docker daemon not reachable (not running, or needs sudo)"
else
  bad "Docker is not installed"
fi
command -v git >/dev/null && ok "$(git --version)" || bad "git is not installed"

section "Ports 80 / 443"
for p in 80 443; do
  who=$(ss -ltnpH "sport = :$p" 2>/dev/null | sed -E 's/.*users:\(\("([^"]+)".*/\1/' | sort -u | tr '\n' ' ')
  if [ -z "$(ss -ltnH "sport = :$p" 2>/dev/null)" ]; then ok "Port $p is free"
  else warn "Port $p is already used by: ${who:-unknown}"; fi
done
if command -v ufw >/dev/null; then
  st=$(ufw status 2>/dev/null | head -1)
  ok "ufw: ${st:-unknown (needs sudo)}"
  ufw status 2>/dev/null | grep -qE '^(80|443)(/tcp)? .*ALLOW|Status: inactive' || [ -z "$st" ] || warn "ufw is active; make sure 80 and 443 are allowed"
fi

section "Outbound access"
for url in https://api.telegram.org https://api.anthropic.com https://graph.instagram.com \
           https://github.com https://acme-v02.api.letsencrypt.org/directory https://registry-1.docker.io/v2/; do
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$url")
  [ "$code" != "000" ] && ok "$url  (HTTP $code)" || bad "$url  unreachable"
done

section "Project"
if [ -f docker-compose.yml ] && [ -d app ]; then
  ok "Repo found in $(pwd) ($(git rev-parse --abbrev-ref HEAD 2>/dev/null) @ $(git rev-parse --short HEAD 2>/dev/null))"
  if [ -f .env ]; then
    for k in IG_ACCESS_TOKEN IG_USER_ID IG_APP_SECRET IG_VERIFY_TOKEN TELEGRAM_BOT_TOKEN \
             TELEGRAM_ADMIN_CHAT_ID TELEGRAM_WEBHOOK_SECRET ANTHROPIC_API_KEY DOMAIN PUBLIC_URL; do
      v=$(grep -E "^$k=" .env | tail -1 | cut -d= -f2-)
      [ -n "$v" ] && ok "$k is set" || warn "$k is empty"
    done
    [ -z "$DOMAIN_ARG" ] && DOMAIN_ARG=$(grep -E '^DOMAIN=' .env | tail -1 | cut -d= -f2-)
  else
    warn ".env not created yet (cp .env.example .env)"
  fi
  if docker compose ps >/dev/null 2>&1; then
    docker compose ps --format '  - {{.Service}}: {{.State}} {{.Status}}' 2>/dev/null
  fi
else
  warn "Not inside the bot repo folder (run this from the cloned 'instagram' directory)"
fi

section "Domain"
if [ -n "$DOMAIN_ARG" ]; then
  RES=$(getent ahostsv4 "$DOMAIN_ARG" | awk '{print $1}' | sort -u | tr '\n' ' ')
  if [ -z "$RES" ]; then bad "$DOMAIN_ARG does not resolve"
  elif echo "$RES" | grep -qw "$PUBIP"; then ok "$DOMAIN_ARG -> $RES (points to this server)"
  else bad "$DOMAIN_ARG -> $RES but this server is $PUBIP"; fi
  code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$DOMAIN_ARG/")
  [ "$code" = "200" ] && ok "https://$DOMAIN_ARG/ answers (bot is up)" || warn "https://$DOMAIN_ARG/ -> HTTP $code (normal if the bot is not started yet)"
else
  warn "No domain given (bash scripts/check-server.sh your.domain.com)"
fi
echo
