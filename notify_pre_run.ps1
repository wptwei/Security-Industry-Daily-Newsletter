# 安防日报预跑提醒（每天 08:28 触发，08:30 生成日报）
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.BalloonTipTitle = "安防日报提醒"
$n.BalloonTipText = "今日安防日报将在 2 分钟后自动生成（08:30），稍后请查收 Outlook 草稿箱"
$n.ShowBalloonTip(12000)
Start-Sleep -Seconds 12
$n.Dispose()
