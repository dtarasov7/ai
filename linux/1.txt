# mem
sudo ps -e -o pid,comm --no-headers | while read pid cmd; do  
  grep -q "^Name:\s\+$cmd$" /proc/$pid/status 2>/dev/null &&  
  awk '/^RssAnon:/ {rss+=$2} END {if (rss) printf "%s %d MiB\n", "'$cmd'", rss/1024}' /proc/$pid/status  
done | sort -k2 -nr | uniq  

