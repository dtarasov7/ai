# swap

for pid in $(ls /proc | grep -E '^[0-9]+$'); do  
  cmd=$(cat /proc/$pid/comm 2>/dev/null)  
  swap=$(grep VmSwap /proc/$pid/status 2>/dev/null | awk '{print $2}')  
  if [ "$swap" != "" ] && [ "$swap" -gt 0 ]; then  
    echo "$swap KB swap used by $cmd (PID $pid)"  
  fi  
done | sort -nr | head  

