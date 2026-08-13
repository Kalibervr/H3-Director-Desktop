# LTX 2.5 geometry preset matrix

This is a static contract matrix for the captured LTX 2.5 Image-to-Video and
Text-to-Video workflows. It is not evidence that every entry can render on a
given machine. Both captured graphs use the same chain:

`ResolutionSelector (multiple 32)` → divide width/height by 2 →
`EmptyLTXVLatentVideo` whole 32-pixel cells → native latent x2 → VAE decode.

The final encoded dimensions are therefore `floor(selector / 64) * 64`, per
axis. A selector output is not necessarily the final output.

`ResolutionSelector` itself supports 0.1–16.0 MP in 0.1 MP increments. The
matrix below deliberately lists only the inspected conservative candidate
tiers: 0.4, 0.6, 0.8, 0.9 and 1.0 MP. All candidate rows are
**contract_verified** unless individually marked otherwise.

| Format | MP | Selector | Pre-latent | Latent → x2 | Final output | Status |
|---|---:|---:|---:|---:|---:|---|
| 16:9 | 0.4 | 864×480 | 432×240 | 13×7 → 26×14 | 832×448 | contract_verified |
| 16:9 | 0.6 | 1056×608 | 528×304 | 16×9 → 32×18 | 1024×576 | contract_verified |
| 16:9 | 0.8 | 1216×672 | 608×336 | 19×10 → 38×20 | 1216×640 | contract_verified |
| 16:9 | 0.9 | 1280×736 | 640×368 | 20×11 → 40×22 | 1280×704 | runtime_verified |
| 16:9 | 1.0 | 1376×768 | 688×384 | 21×12 → 42×24 | 1344×768 | contract_verified |
| 9:16 | 0.4 | 480×864 | 240×432 | 7×13 → 14×26 | 448×832 | contract_verified |
| 9:16 | 0.6 | 608×1056 | 304×528 | 9×16 → 18×32 | 576×1024 | contract_verified |
| 9:16 | 0.8 | 672×1216 | 336×608 | 10×19 → 20×38 | 640×1216 | contract_verified |
| 9:16 | 0.9 | 736×1280 | 368×640 | 11×20 → 22×40 | 704×1280 | runtime_verified (T2V and I2V) |
| 9:16 | 1.0 | 768×1376 | 384×688 | 12×21 → 24×42 | 768×1344 | contract_verified |
| 1:1 | 0.4 | 640×640 | 320×320 | 10×10 → 20×20 | 640×640 | contract_verified |
| 1:1 | 0.6 | 800×800 | 400×400 | 12×12 → 24×24 | 768×768 | contract_verified |
| 1:1 | 0.8 | 928×928 | 464×464 | 14×14 → 28×28 | 896×896 | contract_verified |
| 1:1 | 0.9 | 960×960 | 480×480 | 15×15 → 30×30 | 960×960 | runtime_verified (T2V) |
| 1:1 | 1.0 | 1024×1024 | 512×512 | 16×16 → 32×32 | 1024×1024 | contract_verified |
| 4:3 | 0.4 | 736×576 | 368×288 | 11×9 → 22×18 | 704×576 | contract_verified |
| 4:3 | 0.6 | 928×672 | 464×336 | 14×10 → 28×20 | 896×640 | contract_verified |
| 4:3 | 0.8 | 1056×800 | 528×400 | 16×12 → 32×24 | 1024×768 | contract_verified |
| 4:3 | 0.9 | 1120×832 | 560×416 | 17×13 → 34×26 | 1088×832 | contract_verified |
| 4:3 | 1.0 | 1184×896 | 592×448 | 18×14 → 36×28 | 1152×896 | contract_verified |
| 3:4 | 0.4 | 576×736 | 288×368 | 9×11 → 18×22 | 576×704 | contract_verified |
| 3:4 | 0.6 | 672×928 | 336×464 | 10×14 → 20×28 | 640×896 | contract_verified |
| 3:4 | 0.8 | 800×1056 | 400×528 | 12×16 → 24×32 | 768×1024 | contract_verified |
| 3:4 | 0.9 | 832×1120 | 416×560 | 13×17 → 26×34 | 832×1088 | contract_verified |
| 3:4 | 1.0 | 896×1184 | 448×592 | 14×18 → 28×36 | 896×1152 | contract_verified |

The 9:16 / 0.9 MP row is product-verified for both modes: T2V prompt
`55ccf23b-1593-408a-9a3c-6db7685ba405` and I2V prompt
`c9fe1e10-82ea-436b-9221-f2522c097737`. The 1:1 / 0.9 MP row is T2V
product-verified by prompt `6e3e2426-84c4-47f4-a9d9-8434b725db28`.

Every other row remains contract-only. Before adding one to normal rendering
controls, a real H3 Director render must confirm that exact profile, MP tier,
output size, audio, adoption, and ffprobe result.
