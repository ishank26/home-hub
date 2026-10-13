# Self-hosted fonts

These three WOFF2 faces are served locally; the browser makes no font-service calls.
Full character sets are retained for family names and calendar titles. The accompanying
OFL licenses cover the font files (not the application).

Source: `google/fonts` on GitHub, content-addressed Git blobs fetched and verified
against SHA-1 of `blob <length>\0<content>`, on 2026-10-12:

| Source TTF | Git blob | SHA-256 |
|---|---|---|
| AtkinsonHyperlegible-Regular.ttf | `b3cc4200fcf09d600eac74002ab4ea65b404a536` | `7fb917c89019896d0b52ee84b7cbb3304c18cb90b19a62f5e32712bd23e97669` |
| AtkinsonHyperlegible-Bold.ttf | `ca3f613847de62b8da83d2dab500ec391c8fe477` | `5a3b0c8cc8ca545155150b4512a1fa248298df121c50d6557e651e61fbdab92f` |
| Fraunces-Italic[SOFT,WONK,opsz,wght].ttf | `2ddf59a11b89a3d6b2816ea6ae7965026c08143a` | `b24448c43702fac4ee856781d461a0dfba8d8e594b6e8e190234b75fed2c0e01` |

Conversion: Python fontTools 4.60.1 with Brotli 1.1.0 (development tools only).
Atkinson is converted directly to WOFF2. Fraunces is instantiated with
`instantiateVariableFont(font, {wght: 400, opsz: 60, SOFT: 50, WONK: 1})`, then
converted to WOFF2. All axes are fixed, so only one italic quote face is shipped.

Output SHA-256:

```text
00c0d7ccbca6f4e1d97be90a7ff700a49adb5a8fb146c6375a2b14c2ab0bf217  AtkinsonHyperlegible-Regular.woff2
6a5aaacdfeef2cabbf3e97c0e2bdbae8624e9c7a8eaf775024e7cf5b9d6c2cc2  AtkinsonHyperlegible-Bold.woff2
69306dd6409e5d86f6c4fcc2648c02c99ec6ea21218ac0889e560eb5c7541841  Fraunces-Italic-400.woff2
```
