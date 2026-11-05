# Local and optional remote access

Local browser: **http://localhost:8080**; component links use the same machine's loopback ports. Local access requires no Tailscale or GitHub sign-in. All app/model listeners remain bound to 127.0.0.1.

For a remote browser, use your own SSH account and host:

```bash
ssh -N -o ExitOnForwardFailure=yes \
 -L 8080:127.0.0.1:8080 -L 8200:127.0.0.1:8200 \
 -L 8501:127.0.0.1:8501 -L 8765:127.0.0.1:8765 \
 -L 8800:127.0.0.1:8800 YOUR_USER@YOUR_HOST
```

Open http://localhost:8080 on that browser machine. No model port needs forwarding. SSH forwarding is also useful for browser localhost microphone permissions.

Alternatively configure your own private HTTPS reverse proxies for 8080, 8200, 8501, 8765 and 8800 using your network's authentication and access policy. Tailscale users must install/enroll their own workstation and clients, obtain their own device approvals, and configure their own private Serve routes. This project includes no enrollment keys, hostnames, identities or public Funnel configuration. Launch and stop do not create/remove Serve routes. Existing unrelated network configuration is untouched.

The navigation helper maps loopback component links to the browser's remote hostname/port. If you explicitly set `FURY_REMOTE_ACCESS=1`, the optional device metadata endpoint can read this recipient host's current Tailscale Serve metadata; it remains disabled by default. Remote physical-device/microphone/network quality is an additional acceptance step for the recipient, not established by same-host browser tests.

Do not expose these demonstration services directly to the public internet. Remote proxy access control belongs to your deployment. The public demo administrator password is intentionally public; never reuse it elsewhere.

The [Colorado deployment guide](COLORADO-DEPLOYMENT.html) provides the exact private Serve commands and recipient steps. [Tailscale's current sharing documentation](https://tailscale.com/docs/features/sharing) requires an Owner, Admin or IT admin on both the sharing side and the receiving tailnet to create/accept a machine share. Shared machines use their fully qualified site hostname. Review site access policy so presenters receive demo access separately from SSH/host administration.

## Independent conference stations

Use the existing dashboard HTTPS origin with `/stations`, `/operator`, `/why-hp`, or `/demos`. Keep all five documented private proxies: the chooser opens the original demo ports on the same hostname. Existing Tailscale policy and Serve configuration are not changed by station assignment. The chooser explicitly allows microphone/camera/fullscreen features for its own demo frames; browser permissions and the client device still govern access.

Production framing allows the current private dashboard origin, not arbitrary internet sites. Generated-code frames remain sandboxed with no network/form access and retain the existing validated message bridge. The same browser owns and reconnects to its Factory run; another browser cannot acquire its private controls by selecting a station. Direct application URLs retain their intentionally shareable application behavior.
