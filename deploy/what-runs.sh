#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  «چی نصبه، کجا نصبه، مالِ کدوم پروژه‌ست»
#
#  اجرا:
#      sudo bash deploy/what-runs.sh
#  ذخیره:
#      sudo bash deploy/what-runs.sh > /root/what-runs.txt
#
#  ⚠️ فقط می‌خوانَد. هیچ چیزی نصب/حذف/ری‌استارت نمی‌کند.
#     بدون sudo، مسیر و پوشه‌ی پروسه‌های کاربران دیگر دیده نمی‌شود.
# ─────────────────────────────────────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }
hr()   { printf '─%.0s' $(seq 1 72); echo; }
sec()  { echo; hr; echo "  $1"; hr; }

# ریشه‌ی پروژه = اولین پوشه‌ی بالادستی که .git دارد
proj_root() {
  local d="$1"
  [ -d "$d" ] || d=$(dirname "$d")
  while [ -n "$d" ] && [ "$d" != "/" ]; do
    [ -d "$d/.git" ] && { echo "$d"; return; }
    d=$(dirname "$d")
  done
  echo ""
}
proj_name() {
  local r; r=$(proj_root "$1")
  if [ -n "$r" ]; then echo "$(basename "$r")"; else echo "—"; fi
}
# واحد systemd یک PID
unit_of() {
  [ -r "/proc/$1/cgroup" ] || { echo ""; return; }
  grep -o '[^/]*\.service' "/proc/$1/cgroup" 2>/dev/null | head -1
}

echo "چی کجا نصب است و مال کدام پروژه — $(date '+%Y-%m-%d %H:%M')"
[ "$(id -u)" -ne 0 ] && echo "⚠️  بدون root: مسیر و پوشه‌ی بعضی پروسه‌ها پنهان می‌ماند. sudo بزنید."

# ═══════════════════════════════════════════════════════════
sec "۱) ابزارهای نصب‌شده — کجا هستند و از کدام پکیج آمده‌اند"
echo "  ابزار        مسیر                               پکیج یا منبعِ نصب"
echo "  ──────────────────────────────────────────────────────────────────"
for t in python3 pip3 node npm yarn pnpm php composer java go ruby rustc \
         nginx apache2 mysql psql redis-server redis-cli mongod \
         docker docker-compose certbot supervisord pm2 git curl ufw fail2ban-client; do
  p=$(command -v "$t" 2>/dev/null) || continue
  [ -n "$p" ] || continue
  real=$(readlink -f "$p")
  pkg=""
  if have dpkg; then pkg=$(dpkg -S "$real" 2>/dev/null | head -1 | cut -d: -f1); fi
  if [ -z "$pkg" ]; then
    case "$real" in
      /opt/*)              pkg="دستی در $(echo "$real" | cut -d/ -f1-3)" ;;
      /usr/local/*)        pkg="دستی (usr/local)" ;;
      "$HOME"/*|/root/*)   pkg="نصبِ کاربری" ;;
      /snap/*)             pkg="snap" ;;
      *)                   pkg="—" ;;
    esac
  fi
  printf "  %-12s %-34s %s\n" "$t" "$(echo "$real" | cut -c1-34)" "$pkg"
done

# ═══════════════════════════════════════════════════════════
sec "۲) پورت‌های باز ← کدام پروسه ← کدام پروژه"
if have ss; then
  ss -tulpnH 2>/dev/null | while read -r line; do
    addr=$(echo "$line" | awk '{print $5}')
    pid=$(echo "$line" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
    [ -z "$pid" ] && { printf "  %-24s %s\n" "$addr" "(پروسه نامعلوم — با sudo اجرا کنید)"; continue; }
    exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null)
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null)
    cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | cut -c1-70)
    unit=$(unit_of "$pid")
    root=$(proj_root "${cwd:-$exe}")
    echo "  ▸ $addr"
    echo "      پروسه : ${cmd:-?}  (PID $pid)"
    echo "      فایل  : ${exe:-?}"
    echo "      پوشه  : ${cwd:-?}"
    [ -n "$unit" ] && echo "      سرویس : $unit"
    if [ -n "$root" ]; then
      echo "      پروژه : $(basename "$root")  →  $root"
    else
      echo "      پروژه : (به هیچ ریپو گیتی وصل نیست)"
    fi
    echo
  done
elif have netstat; then
  netstat -tulpn 2>/dev/null | sed 's/^/  /'
  echo "  (ss نصب نیست — خروجی netstat جزئیات کمتری دارد)"
else
  echo "  نه ss و نه netstat در دسترس نیست."
fi
echo "  یادآوری: ربات تلگرام هیچ پورتی باز نمی‌کند — اگر اینجا دیده شد، جای دیگری اشتباه است."

# ═══════════════════════════════════════════════════════════
sec "۳) سرویس‌های systemd ← مسیر اجرا ← پروژه"
if have systemctl; then
  systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null \
  | awk '{print $1}' | while read -r u; do
    exec=$(systemctl show "$u" -p ExecStart --value 2>/dev/null | grep -o 'path=[^ ]*' | head -1 | cut -d= -f2)
    wd=$(systemctl show "$u" -p WorkingDirectory --value 2>/dev/null)
    usr=$(systemctl show "$u" -p User --value 2>/dev/null)
    frag=$(systemctl show "$u" -p FragmentPath --value 2>/dev/null)
    root=$(proj_root "${wd:-$exec}")
    # سرویس‌های خودِ سیستم را کوتاه رد کن
    case "$frag" in
      /lib/systemd/*|/usr/lib/systemd/*) sys=" [سیستمی]" ;;
      *) sys="" ;;
    esac
    echo "  ▸ $u$sys"
    [ -n "$exec" ] && echo "      اجرا  : $exec"
    [ -n "$wd" ]   && [ "$wd" != "/" ] && echo "      پوشه  : $wd"
    [ -n "$usr" ]  && echo "      کاربر : $usr"
    [ -n "$frag" ] && echo "      یونیت : $frag"
    [ -n "$root" ] && echo "      پروژه : $(basename "$root")  →  $root"
    echo
  done
else
  echo "  systemd در دسترس نیست."
fi

# ═══════════════════════════════════════════════════════════
sec "۴) پروژه‌ها — هرکدام کجاست، چیست، و چه چیزی اجرایش می‌کند"
ROOTS=$(find /opt /srv /var/www /home /root -maxdepth 3 -name .git -type d 2>/dev/null \
        | sed 's#/\.git$##' | sort -u)
if [ -z "$ROOTS" ]; then
  echo "  هیچ ریپو گیتی پیدا نشد."
else
  echo "$ROOTS" | while read -r r; do
    name=$(basename "$r")
    url=$(git -C "$r" remote get-url origin 2>/dev/null)
    br=$(git -C "$r" rev-parse --abbrev-ref HEAD 2>/dev/null)
    cm=$(git -C "$r" log --oneline -1 2>/dev/null)
    sz=$(du -sh "$r" 2>/dev/null | cut -f1)
    # زبان/فریم‌ورک از روی فایل‌های شاخص
    kind=""
    [ -f "$r/requirements.txt" ] || [ -f "$r/pyproject.toml" ] && kind="$kind python"
    [ -f "$r/package.json" ]   && kind="$kind node"
    [ -f "$r/composer.json" ]  && kind="$kind php"
    [ -f "$r/Gemfile" ]        && kind="$kind ruby"
    [ -f "$r/go.mod" ]         && kind="$kind go"
    [ -f "$r/Cargo.toml" ]     && kind="$kind rust"
    [ -f "$r/Dockerfile" ] || [ -f "$r/docker-compose.yml" ] && kind="$kind docker"
    [ -d "$r/venv" ] || [ -d "$r/.venv" ] && kind="$kind venv"
    # کدام سرویس به این پوشه اشاره می‌کند؟
    svc=""
    if have systemctl; then
      svc=$(grep -rls "$r" /etc/systemd/system/*.service 2>/dev/null \
            | xargs -r -n1 basename | tr '\n' ' ')
    fi
    # کدام پورت از این پوشه باز شده؟
    ports=""
    if have ss && [ "$(id -u)" -eq 0 ]; then
      for pid in $(ss -tulpnH 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do
        c=$(readlink -f "/proc/$pid/cwd" 2>/dev/null)
        case "$c" in "$r"|"$r"/*)
          ports="$ports $(ss -tulpnH 2>/dev/null | grep "pid=$pid," | awk '{print $5}' | tr '\n' ' ')" ;;
        esac
      done
    fi
    echo "  ▸ $name"
    echo "      مسیر  : $r   ($sz)"
    [ -n "$url" ]  && echo "      ریپو  : $url"
    [ -n "$br" ]   && echo "      شاخه  : $br"
    [ -n "$cm" ]   && echo "      کامیت : $cm"
    [ -n "$kind" ] && echo "      نوع   :$kind"
    [ -n "$svc" ]  && echo "      سرویس : $svc"
    [ -n "$ports" ]&& echo "      پورت  :$ports"
    [ -z "$svc$ports" ] && echo "      وضعیت : سرویس یا پورتی به آن وصل نیست (شاید فقط کد است)"
    echo
  done
fi

# ═══════════════════════════════════════════════════════════
sec "۵) پوشه‌های حجیم بدون ریپو گیت (احتمالاً نصب دستی)"
for base in /opt /srv /var/www; do
  [ -d "$base" ] || continue
  for d in "$base"/*; do
    [ -d "$d" ] || continue
    [ -d "$d/.git" ] && continue
    printf "  %-8s %s\n" "$(du -sh "$d" 2>/dev/null | cut -f1)" "$d"
  done
done | sort -rh | head -20
echo
echo "  (این‌ها ریپو نیستند: یا نصب دستی ابزارند، یا داده، یا بازمانده‌ی نصب قدیمی)"

echo
hr
echo "  ذخیره:  sudo bash deploy/what-runs.sh > /root/what-runs.txt"
hr
