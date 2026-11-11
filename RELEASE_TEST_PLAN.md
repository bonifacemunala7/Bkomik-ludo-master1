# BKOMIK Ludo Master — Release Test Plan

## Automated checks

- [ ] `python -m py_compile main.py`
- [ ] `python -m unittest discover -s tests -v`

## Pydroid 3 / Android checks

Use two physical Android devices connected to the same Wi-Fi network.

- [ ] App launches without an import or startup error.
- [ ] Board and controls fit the device screen.
- [ ] Local game: human vs AI, human-only and all four colours.
- [ ] Easy, Medium and Hard AI each take turns.
- [ ] A six allows a token to leave the yard.
- [ ] Exactly one legal token moves automatically.
- [ ] No legal move passes the turn automatically.
- [ ] Rolling six grants the same player another turn.
- [ ] Captures return opposing tokens to their yards.
- [ ] Safe squares prevent captures.
- [ ] Tokens enter the correct home lane and finish only on an exact count.
- [ ] Win detection triggers only after all four tokens finish.
- [ ] Statistics/history persist after closing and reopening the app.
- [ ] Daily challenge changes on the next local date.
- [ ] Sound can be disabled and the game remains playable if audio is unavailable.
- [ ] App pause/resume does not corrupt the current match.

## LAN checks (two devices)

- [ ] Host starts a room and displays its LAN IP and six-digit room code.
- [ ] Guest joins with correct IP/code.
- [ ] Incorrect room code is rejected; host can still accept a valid guest.
- [ ] Host RED turn: dice roll, move, state sync to guest.
- [ ] Guest GREEN turn: dice roll, move, state sync to host.
- [ ] Single-legal-token automatic movement synchronizes correctly.
- [ ] No-legal-move turn pass synchronizes correctly.
- [ ] Six extra turn synchronizes correctly.
- [ ] Captures, home-lane movement and wins synchronize correctly.
- [ ] Guest disconnects; host reports disconnection and keeps the room listener available.
- [ ] Guest manually rejoins using the same host IP and room code.
- [ ] Test router client isolation, Wi-Fi changes and Android background/foreground behaviour.

## Known limitations / not yet verified

- Host can accept a guest reconnect; the guest must manually retry joining.
- The app has no automatic reconnect, internet matchmaking, relay server or cloud service.
- LAN behaviour depends on Android version, Wi-Fi router configuration and permissions.
- Kivy UI, animations, sockets and lifecycle still require physical-device testing.
- `buildozer.spec` is a starter profile, not proof of a successful Android build.
- A signed APK/AAB, Play Console declarations, final privacy policy and store assets are not included.
