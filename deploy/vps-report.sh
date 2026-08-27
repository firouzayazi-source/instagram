#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  گزارش کامل «روی این وی‌پی‌اس چه چیزهایی نصب است»
#
#  اجرا:
#      sudo bash deploy/vps-report.sh
#  ذخیره در فایل:
#      sudo bash deploy/vps-report.sh > /root/vps-report.txt
#
#  ⚠️ این اسکریپت فقط می‌خوانَد. هیچ چیزی نصب، حذف، ری‌استارت یا
#     تغییر نمی‌کند — پس روی پروژه‌های دیگرِ همین سرور اثری ندارد.
#     بدون sudo هم اجرا می‌شود، ولی نام پروسه‌ی پشت پورت‌ها و
#     کران‌های کاربران دیگر را نمی‌بیند.
# ─────────────────────────────────────────────────────────────
PROJECT_DIR="/opt/telegram-bot"
have() { command -v "$1" >/dev/null 2>&1; }
# نسخه‌ی هر ابزار — چندتایی سوئیچ متفاوتی دارند یا خروجی‌شان نویز دارد
ver() {
  case "$1" in
    go)       go version 2>/dev/null ;;
    tmux)     tmux -V 2>/dev/null ;;
    screen)   screen --version 2>/dev/null ;;
    java)     java -version 2>&1 | grep -v 'Picked up' | head -1 ;;
    composer) composer --version --no-plugins 2>/dev/null | grep -io 'composer version.*' | head -1 ;;
    *)        "$1" --version 2>&1 | grep -v 'Picked up' | head -1 ;;
  esac
}
hr()   { printf '─%.0s' $(seq 1 60); echo; }
sec()  { echo; hr; echo "  $1"; hr; }
none() { echo "  (چیزی پیدا نشد)"; }

echo "گزارش وی‌پی‌اس — $(date '+%Y-%m-%d %H:%M:%S %Z')"
[ "$(id -u)" -ne 0 ] && echo "⚠️  بدون root اجرا شده — بخش‌هایی ناقص خواهد بود (sudo بزنید)."

sec "۱) سیستم"
echo "  هاست‌نیم : $(hostname)"
if [ -r /etc/os-release ]; then . /etc/os-release; echo "  سیستم‌عامل: $PRETTY_NAME"; fi
echo "  کرنل    : $(uname -r) ($(uname -m))"
echo "  آپ‌تایم  : $(uptime -p 2>/dev/null || uptime)"
have timedatectl && echo "  تایم‌زون : $(timedatectl show -p Timezone --value 2>/dev/null)"

sec "۲) منابع"
echo "  پردازنده: $(nproc 2>/dev/null) هسته"
have free && free -h | sed 's/^/  /'
echo
echo "  دیسک:"
df -h -x tmpfs -x devtmpfs 2>/dev/null | sed 's/^/  /'

sec "۳) پورت‌های باز  ← مهم‌ترین بخش برای تداخل پروژه‌ها"
if have ss; then
  ss -tulpnH 2>/dev/null | awk '{printf "  %-6s %-24s %s\n",$1,$5,$7}' | sort -u
elif have netstat; then
  netstat -tulpn 2>/dev/null | sed 's/^/  /'
else
  none
fi
echo
echo "  (ربات تلگرام هیچ پورتی باز نمی‌کند — اگر اینجا دیده شد یعنی جای دیگری اشتباه است)"

sec "۴) سرویس‌های در حال اجرا (systemd)"
if have systemctl; then
  systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null \
    | awk '{print "  "$1}' | sort
  echo
  echo "  سرویس‌های فعال‌شده در بوت:"
  systemctl list-unit-files --type=service --state=enabled --no-pager --no-legend 2>/dev/null \
    | awk '{print "  "$1}' | sort
else none; fi

sec "۵) وب‌سرور"
for w in nginx apache2 httpd caddy haproxy; do
  have $w && echo "  ✅ $w — $($w -v 2>&1 | head -1)"
done
if [ -d /etc/nginx/sites-enabled ]; then
  echo "  سایت‌های فعال nginx:"
  ls -1 /etc/nginx/sites-enabled 2>/dev/null | sed 's/^/    • /' || none
  echo "  پورت/دامنه‌های تعریف‌شده:"
  grep -rhE '^\s*(listen|server_name)' /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null \
    | tr -s ' ' | sed 's/^ //;s/;$//' | sort -u | sed 's/^/    /'
fi
[ -d /etc/apache2/sites-enabled ] && { echo "  سایت‌های فعال apache:"; ls -1 /etc/apache2/sites-enabled | sed 's/^/    • /'; }

sec "۶) دیتابیس‌ها و کش"
for d in mysql mariadb psql postgres redis-cli mongod mongosh sqlite3 memcached; do
  have $d && echo "  ✅ $d — $($d --version 2>&1 | head -1)"
done

sec "۷) زبان‌ها و ابزارها"
for t in python3 pip3 node npm yarn pnpm php composer java go ruby rustc git curl wget \
         docker docker-compose podman certbot ufw fail2ban-client supervisorctl pm2 tmux screen; do
  have $t && printf "  ✅ %-16s %s\n" "$t" "$(ver "$t" | cut -c1-58)"
done

sec "۸) داکر"
if have docker; then
  echo "  کانتینرها:"
  docker ps -a --format '    {{.Names}}  |  {{.Image}}  |  {{.Status}}  |  {{.Ports}}' 2>/dev/null \
    || echo "    (به daemon داکر دسترسی نیست — یا خاموش است یا sudo لازم دارد)"
  echo "  ایمیج‌ها:"
  docker images --format '    {{.Repository}}:{{.Tag}}  ({{.Size}})' 2>/dev/null | head -20
else
  echo "  داکر نصب نیست."
fi

sec "۹) پکیج‌های سیستم"
if have dpkg; then
  echo "  مجموع پکیج‌های نصب‌شده: $(dpkg -l 2>/dev/null | grep -c '^ii')"
  echo
  echo "  ▸ سرویس‌ها و ابزارهای مهمی که نصب‌اند:"
  KEY='nginx|apache2|mysql|mariadb|postgresql|redis|mongodb|memcached|php[0-9.]*-?|nodejs|npm'
  KEY="$KEY"'|python3\.|python3-pip|python3-venv|docker-ce|containerd|certbot|supervisor'
  KEY="$KEY"'|ufw|fail2ban|openjdk|golang|ruby|rustc|git$|curl$|wget$|unzip|cron'
  if have apt-mark; then
    apt-mark showmanual 2>/dev/null | grep -E "^($KEY)" | sort -u | sed 's/^/    • /' || none
  fi
  echo
  echo "  ▸ آخرین چیزهایی که روی این سرور نصب شده (تاریخ‌دار):"
  if [ -r /var/log/apt/history.log ]; then
    awk '/^Start-Date:/{d=$2} /^Install:/{sub(/^Install: /,"");gsub(/\([^)]*\)/,"");
         gsub(/:amd64|:all|:i386/,"");gsub(/, /," ");print "    "d"  "$0}' \
         /var/log/apt/history.log 2>/dev/null \
      | cut -c1-120 | tail -15
    ls /var/log/apt/history.log.*.gz >/dev/null 2>&1 \
      && echo "    (قدیمی‌ترها: zcat /var/log/apt/history.log.*.gz | grep Install)"
  else
    echo "    (تاریخچه‌ی apt در دسترس نیست)"
  fi
  echo
  echo "  ▸ فهرست کامل پکیج‌های دستی:  apt-mark showmanual | sort"
elif have rpm; then
  echo "  مجموع پکیج‌ها: $(rpm -qa | wc -l)"
  rpm -qa --last 2>/dev/null | head -40 | sed 's/^/    /'
else none; fi

sec "۱۰) پایتون — بسته‌های سراسری"
if have pip3; then
  pip3 list --format=columns 2>/dev/null | sed 's/^/  /' | head -60
else
  echo "  pip3 نصب نیست."
fi

sec "۱۱) کران‌جاب‌ها (کارهای زمان‌بندی‌شده)"
echo "  کران root:"
_cr=$(crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$')
[ -n "$_cr" ] && echo "$_cr" | sed 's/^/    /' || echo "    (خالی)"
if [ "$(id -u)" -eq 0 ]; then
  for u in $(cut -d: -f1 /etc/passwd); do
    out=$(crontab -u "$u" -l 2>/dev/null | grep -v '^#' | grep -v '^$')
    [ -n "$out" ] && [ "$u" != "root" ] && { echo "  کران $u:"; echo "$out" | sed 's/^/    /'; }
  done
fi
echo "  فایل‌های /etc/cron.d:"
_cd=$(ls -1 /etc/cron.d 2>/dev/null)
[ -n "$_cd" ] && echo "$_cd" | sed 's/^/    • /' || echo "    (خالی)"
if have systemctl; then
  echo "  تایمرهای systemd:"
  systemctl list-timers --all --no-pager --no-legend 2>/dev/null | awk '{print "    "$NF}' | sort -u | head -20
fi

sec "۱۲) پروژه‌های روی سرور"
for base in /opt /srv /var/www /home /root; do
  [ -d "$base" ] || continue
  found=$(find "$base" -maxdepth 2 -name .git -type d 2>/dev/null | head -20)
  [ -n "$found" ] && {
    echo "  $base:"
    echo "$found" | while read -r g; do
      p=$(dirname "$g")
      url=$(git -C "$p" remote get-url origin 2>/dev/null)
      br=$(git -C "$p" rev-parse --abbrev-ref HEAD 2>/dev/null)
      echo "    • $p  [$br]  ${url:-بدون remote}"
    done
  }
done
echo
echo "  حجم پوشه‌ها:"
du -sh /opt/* /var/www/* /srv/* 2>/dev/null | sort -rh | head -15 | sed 's/^/    /'

sec "۱۳) فایروال"
if have ufw; then ufw status verbose 2>/dev/null | sed 's/^/  /'
elif have firewall-cmd; then firewall-cmd --list-all 2>/dev/null | sed 's/^/  /'
elif have iptables; then iptables -L -n 2>/dev/null | head -30 | sed 's/^/  /'
else none; fi

sec "۱۴) ربات تلگرام (این پروژه)"
if [ -d "$PROJECT_DIR" ]; then
  echo "  مسیر    : $PROJECT_DIR"
  echo "  سرویس   : $(systemctl is-active telegram-bot 2>/dev/null || echo نامشخص)"
  echo "  کامیت   : $(git -C "$PROJECT_DIR" log --oneline -1 2>/dev/null)"
  echo "  شاخه    : $(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  echo "  حجم     : $(du -sh "$PROJECT_DIR" 2>/dev/null | cut -f1)"
  if [ -x "$PROJECT_DIR/venv/bin/pip" ]; then
    echo "  بسته‌های venv:"
    "$PROJECT_DIR/venv/bin/pip" list --format=columns 2>/dev/null | sed 's/^/    /'
  fi
  echo "  فایل‌های داده:"
  for f in users.db data.json banner.json workhours.json buttons.json settings.json \
           stats.json menu.json places.json admins.json faq.json unmatched.json \
           backups.json broadcast.json; do
    [ -e "$PROJECT_DIR/$f" ] && printf "    ✅ %-18s %s\n" "$f" "$(du -h "$PROJECT_DIR/$f" | cut -f1)"
  done
else
  echo "  در $PROJECT_DIR چیزی نیست."
fi

echo
hr
echo "  پایان گزارش. برای ذخیره:"
echo "     sudo bash deploy/vps-report.sh > /root/vps-report.txt"
hr
