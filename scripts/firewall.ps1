param([switch]$Remove)
$n = "ClipBridge"
if ($Remove) { Remove-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue; exit }
New-NetFirewallRule -DisplayName $n -Direction Inbound -Protocol TCP -LocalPort 48500 -Action Allow -Profile Private -RemoteAddress LocalSubnet
New-NetFirewallRule -DisplayName "$n mDNS" -Direction Inbound -Protocol UDP -LocalPort 5353 -Action Allow -Profile Private -RemoteAddress LocalSubnet
