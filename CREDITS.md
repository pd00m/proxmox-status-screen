# Credits and attribution

## turing-smart-screen-python

`proxmox-status-screen` is a separate project, but it **vendors** the hardware display
driver and the Pillow drawing primitives of
[turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python)
(see `display_driver/`). That code is licensed under GPL-3.0-or-later and remains
the copyright of its original authors.

- Project: <https://github.com/mathoudebine/turing-smart-screen-python>
- Copyright (C) 2021 Matthieu Houdebine (@mathoudebine) and contributors
- License: GPL-3.0-or-later (see `LICENSE`)

### Significant contributors

This is the upstream project's own list of significant contributors, ordered by
first contribution:

- Matthieu Houdebine (@mathoudebine)
- Ebag333
- Charles Ferguson (@gerph)
- Russ Nelson (@RussNelson)
- Rollback (@Rollbacke)
- w1ld3r

### All contributors

The following people have contributed to turing-smart-screen-python, according to
its revision history. Thank you all:

- A-Blade-Of-Grass
- AlanFromJapan
- Alex W. Baulé
- Amilton de Camargo Jr
- Anton
- Arthur Ferrai
- Charles Ferguson
- cobacdavid
- Colin Shorts
- Dawid Ł.
- drivin
- Ebag333
- Estêvão Z. Rufino
- gwendal-h
- hicwic
- homelab-black
- Hugo Chargois
- John Issac
- Jordan Lambert
- Matthieu Houdebine
- Matthew G. Johnson
- Michael Maher (majormer)
- mikem2te
- MondoBoricua
- Nano
- napobear
- Nathan Neulinger
- Nhomar Hernandez [Vauxoo]
- OctaNebula
- Pepper-the-kobold
- Rollback (Rollbacke)
- Russ Nelson
- Ryan Wolstenholme
- Sai Asish Y
- SinyaWeo
- sutaburosu
- Sylvain
- Takacs Attila
- Vicente Salvador
- w1ld3r
- Wilfried J.
- wyldere
- Xzonn
- Максим Перминов

## Fonts

- `fonts/roboto` and `fonts/roboto-mono`: Roboto and Roboto Mono, Copyright
  Google, licensed under the Apache License 2.0 (see the `LICENSE.txt` files in
  those folders).

## Third-party dependencies

This project depends on `requests`, `PyYAML`, `Pillow`, `pyserial`, `numpy` and
optionally `pyusb` / `pycryptodome`. Each is distributed under its own license.
