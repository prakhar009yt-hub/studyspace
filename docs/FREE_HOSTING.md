# Personal hosting without server charges

**Latest selected setup:** host the website on Vercel while every visitor runs their own local companion. No Tailscale is required. Follow [LOCAL_COMPANION.md](LOCAL_COMPANION.md). The instructions below remain an optional way to reach one PC from your own other devices.

Use the full Studyspace app on your existing Windows PC, and reach it privately from your phone or another computer using Tailscale Serve. Your existing notes, exam plans, settings, keys and manual MUJ login stay on the PC. No paid VPS, Render disk, custom domain or Docker installation is required for this route.

This is **personal remote access**, not an always-on public cloud deployment. Your PC must remain on, awake, connected to the internet, and running Studyspace. Electricity/internet and any Google API charges are separate. A VPN does not increase API quotas or convert paid provider calls into free ones. Tailscale currently offers a free personal option; verify eligibility and limits in [its current pricing](https://tailscale.com/pricing). No paid plan or billing upgrade is selected by the helper.

## Setup once

1. Install [Tailscale for Windows](https://tailscale.com/download/windows) on the PC that already runs Studyspace.
2. Sign in and use your personal/free network. Install Tailscale on your phone/other device and sign in to the same personal network. Use a network containing only trusted users/devices: any user/device permitted by its access policy can reach the shared workspace, including its notes and Settings. Studyspace has no separate account isolation.
3. Open PowerShell in the Studyspace project folder and run:

   ```powershell
   .\Start-Free.ps1
   ```

4. If Tailscale displays an HTTPS/Serve setup link, follow it and rerun the command. The service obtains an HTTPS URL using the device's `*.ts.net` hostname. Tailscale HTTPS certificates can publish the device hostname in public certificate-transparency logs; use a non-sensitive device name.
5. Open the printed private HTTPS URL on a device connected to Tailscale. Sign in to MUJ through Studyspace on the host PC when needed. The visible sign-in browser opens on the host PC, not your phone.

The helper reuses the current app on port 8503 only after checking its process belongs to this project and listens on loopback. Otherwise it starts the app hidden on that port with logs under ignored `data/`. If another service occupies the port, it stops with an explanation. To choose another app port, use `-Port 8504` consistently in Start/Status/Stop.

The helper does not install Tailscale, sign in for you, change the network's access policy, enable a public Funnel, modify router/firewall settings, disable CORS/XSRF, create scheduled tasks, or change sleep/power settings. It refuses to overwrite another HTTPS 443 Serve configuration or advertise a route that has public Funnel enabled. It does not reset other Serve settings.

## Daily use

```powershell
# Start/reuse the app and private route
.\Start-Free.ps1

# Show the private URL and route status
.\Start-Free.ps1 -Action Status

# Remove only this helper's matching private route; keep the local app/data
.\Start-Free.ps1 -Action Stop
```

Route ownership metadata is stored in ignored `data/free-host.json`. A preexisting route is reused but is not claimed as owned, so Stop will not remove a route that this helper did not create. If another tool changes that route, Stop refuses to alter it. Local data and the running Streamlit process are preserved when stopping remote access.

Background Tailscale Serve can persist across its restarts, but the Python app is not installed as a Windows service. Run Start-Free again after rebooting. Do not assume the app is available while your PC sleeps or is offline. No scheduled startup or power-policy changes are made automatically.

## Optional Vercel address

You do not need Vercel for private access: the printed HTTPS address opens the full app directly.

If you want the Vercel website as well, deploy `web/` using [VERCEL.md](VERCEL.md), and set its public `STUDYSPACE_BACKEND_URL` to the private HTTPS address printed by the helper. Redeploy the website after setting it. The Vercel static website can be publicly reachable, but opening the backend still requires the visitor's device to be connected to your personal Tailscale network. The backend address is public build configuration, so omit the Vercel frontend if you do not want to publish your device hostname.

Do not use Tailscale Funnel for this personal app: that publishes a service to the public internet, whereas Serve keeps it inside your network. Do not forward port 8503 on your router. If embedding is restricted by the browser, use the website's **Open directly** link.

## Verification and limits

`tests/test_free_host.ps1` checks route matching, conflicting routes, public Funnel detection and PowerShell syntax without installing or contacting Tailscale. A real phone-to-PC connectivity check requires your own Tailscale installation, account login, HTTPS setup and device. No successful live remote connection is claimed before that check.

Official references: [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), [CLI setup and removal](https://tailscale.com/docs/reference/tailscale-cli/serve), [current plans](https://tailscale.com/pricing).
