# Generative Adversarial Network (GAN)

> Two neural networks locked in a zero-sum game — one forging, one detecting — until the forgeries become indistinguishable from reality.

**Type:** Learn
**Prerequisites:** Neural Network Basics, Backpropagation, Latent Space & Embeddings
**Time:** ~35 minutes

---

## The Problem

Suppose you are building a medical imaging platform that needs thousands of labeled X-ray images to train a tumor-detection model, but your hospital has only 200 annotated scans. Collecting and labeling real data is expensive, slow, and subject to privacy regulations. You need a way to synthesize realistic training samples that preserve the statistical properties of real scans without exposing patient data.

Or consider a game studio that wants procedurally generated character skins, a fashion retailer that needs photorealistic images of unproduced garments, or an autonomous-vehicle team that needs rare-but-dangerous road scenarios. In every case the bottleneck is the same: the real world does not supply enough examples of the things you care about.

Traditional statistical techniques (Gaussian noise, simple augmentation, variational autoencoders) can produce new samples, but they tend to be blurry, averaged, or obviously synthetic. What you actually need is a model that learns the full joint distribution of the training data and can draw crisp, diverse samples from it — and that is exactly what a Generative Adversarial Network is designed to do.

---

## The Concept

### The Adversarial Setup

Ian Goodfellow introduced GANs in 2014 with a deceptively simple framing: train two networks against each other. One network — the **Generator (G)** — tries to create convincing fakes. The other — the **Discriminator (D)** — tries to distinguish fakes from real samples. Neither network can win by standing still; each must improve in response to the other, creating a feedback loop that drives both toward higher quality.

```
                     ┌──────────────────────────────────────────┐
                     │              Training Loop               │
                     └──────────────────────────────────────────┘

  Random Noise z ──► [ Generator G ] ──► Fake sample G(z)
                                                │
                                                ▼
  Real sample x ─────────────────────► [ Discriminator D ] ──► P(real)
                                                │
                                         ┌──────┴───────┐
                                         │   Loss       │
                                         │  signals     │
                                         └──┬───────┬───┘
                                            │       │
                              Update D ◄────┘       └────► Update G
                         (get better at             (fool D more
                          spotting fakes)            convincingly)
```

### The Objective Function

The formal minimax game is:

```
min_G  max_D  E[log D(x)] + E[log(1 - D(G(z)))]
```

- **D's goal:** maximize log D(x) (correctly label real samples) and maximize log(1 - D(G(z))) (correctly label fakes).
- **G's goal:** minimize log(1 - D(G(z))), i.e., produce samples so realistic that D outputs a high probability even for fakes.

In practice, G is often trained to maximize log D(G(z)) instead (the "non-saturating" variant), because the gradient is stronger early in training when D easily rejects fakes.

### The Two-Network Architecture

| Component | Role | Typical Input | Typical Output |
|---|---|---|---|
| Generator G | Creates synthetic data | Random noise vector z (e.g., 100-dim Gaussian) | Synthetic sample in data space (e.g., 64×64 image) |
| Discriminator D | Classifies real vs. fake | A sample from data space | Scalar in [0, 1] — probability of being real |

The Generator never sees real data directly. It only receives gradient signals that flow backward through the Discriminator. The Discriminator sees both real data and Generator outputs, but does not know the Generator's weights.

### Latent Space

The noise vector **z** lives in a **latent space** — a compressed, continuous representation of variation. Walking along a direction in latent space produces smooth interpolations in output space. This is why you can do things like "interpolate between two faces" by linearly blending their z vectors.

```
z₁ = [0.2, -0.5, 0.8, ...]  →  Face A (young, smiling)
z₂ = [0.9,  0.3, 0.1, ...]  →  Face B (older, neutral)

Blend at t=0.5:
z_mid = 0.5*z₁ + 0.5*z₂     →  Intermediate face
```

### Training Dynamics

Training alternates between two sub-steps per mini-batch:

1. **Step 1 — Update D:** Freeze G. Sample a batch of real images and a batch of G(z) fakes. Compute D's binary cross-entropy loss. Backpropagate through D only.
2. **Step 2 — Update G:** Freeze D. Generate a fresh batch of fakes. Pass them through D. Compute G's loss against the "real" label (G wants D to say they are real). Backpropagate gradients through D and then into G.

This alternating scheme is critical. If you update both simultaneously, gradients interfere and training destabilizes.

### Why It Works (Intuition)

Think of G as a counterfeiter and D as a detective. Early on, G produces garbage and D trivially rejects it. D's feedback tells G "your fakes look nothing like real currency — try this correction." G improves. Now D must refine its detection criterion. The system reaches a theoretical optimum — the **Nash equilibrium** — when G's distribution perfectly matches the real data distribution, and D can do no better than random guessing (outputting 0.5 everywhere). In practice, training rarely reaches the theoretical optimum cleanly, but the adversarial pressure consistently produces high-quality outputs.

---

## Build It / In Depth

### Minimal GAN on MNIST (PyTorch)

The following is a self-contained, runnable example that trains a GAN to generate handwritten digits.

```python
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.utils import save_image

# ── Hyperparameters ────────────────────────────────────────────────────────────
LATENT_DIM  = 64
IMG_SIZE    = 28 * 28   # MNIST is 28×28 grayscale → 784 pixels
HIDDEN      = 256
BATCH       = 128
LR          = 2e-4
EPOCHS      = 50
DEVICE      = "cuda" if torch.cuda.is_available() else "cpu"

# ── Data ───────────────────────────────────────────────────────────────────────
transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize([0.5], [0.5]),   # scale to [-1, 1]
])
dataset = datasets.MNIST("./data", train=True, download=True, transform=transform)
loader  = DataLoader(dataset, batch_size=BATCH, shuffle=True, drop_last=True)

# ── Generator ──────────────────────────────────────────────────────────────────
class Generator(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(LATENT_DIM, HIDDEN),
            nn.LeakyReLU(0.2),
            nn.Linear(HIDDEN, HIDDEN * 2),
            nn.BatchNorm1d(HIDDEN * 2),
            nn.LeakyReLU(0.2),
            nn.Linear(HIDDEN * 2, IMG_SIZE),
            nn.Tanh(),   # output in [-1, 1] to match normalized images
        )
    def forward(self, z):
        return self.net(z)

# ── Discriminator ──────────────────────────────────────────────────────────────
class Discriminator(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(IMG_SIZE, HIDDEN * 2),
            nn.LeakyReLU(0.2),
            nn.Dropout(0.3),
            nn.Linear(HIDDEN * 2, HIDDEN),
            nn.LeakyReLU(0.2),
            nn.Dropout(0.3),
            nn.Linear(HIDDEN, 1),
            nn.Sigmoid(),   # probability in [0, 1]
        )
    def forward(self, img):
        return self.net(img.view(img.size(0), -1))

# ── Instantiate ────────────────────────────────────────────────────────────────
G   = Generator().to(DEVICE)
D   = Discriminator().to(DEVICE)
opt_G = torch.optim.Adam(G.parameters(), lr=LR, betas=(0.5, 0.999))
opt_D = torch.optim.Adam(D.parameters(), lr=LR, betas=(0.5, 0.999))
loss_fn = nn.BCELoss()

# ── Training loop ──────────────────────────────────────────────────────────────
for epoch in range(EPOCHS):
    for real_imgs, _ in loader:
        real_imgs = real_imgs.to(DEVICE)
        z = torch.randn(BATCH, LATENT_DIM, device=DEVICE)

        # ── Step 1: Update Discriminator ──────────────────────────────────────
        fake_imgs = G(z).detach()   # detach: no gradient flows into G here
        real_labels = torch.ones(BATCH, 1, device=DEVICE)
        fake_labels = torch.zeros(BATCH, 1, device=DEVICE)

        loss_real = loss_fn(D(real_imgs.view(BATCH, -1)), real_labels)
        loss_fake = loss_fn(D(fake_imgs), fake_labels)
        d_loss = (loss_real + loss_fake) / 2

        opt_D.zero_grad(); d_loss.backward(); opt_D.step()

        # ── Step 2: Update Generator ──────────────────────────────────────────
        z = torch.randn(BATCH, LATENT_DIM, device=DEVICE)
        gen_imgs = G(z)
        # G wants D to output 1 (real) for its fakes
        g_loss = loss_fn(D(gen_imgs), real_labels)

        opt_G.zero_grad(); g_loss.backward(); opt_G.step()

    print(f"Epoch {epoch+1}/{EPOCHS}  D_loss={d_loss.item():.4f}  G_loss={g_loss.item():.4f}")
    if (epoch + 1) % 10 == 0:
        save_image(gen_imgs.view(BATCH, 1, 28, 28)[:25],
                   f"samples_epoch_{epoch+1}.png", nrow=5, normalize=True)
```

### What to Watch During Training

```
Epoch  1  D_loss=0.69  G_loss=0.69   ← both near ln(2) ≈ 0.693, as expected at random
Epoch 10  D_loss=0.45  G_loss=1.20   ← D improving, G struggling
Epoch 30  D_loss=0.58  G_loss=0.85   ← approaching equilibrium
Epoch 50  D_loss=0.63  G_loss=0.72   ← near-equilibrium, samples look like digits
```

When D_loss collapses to ~0, D has overpowered G and gradients vanish — this is **mode collapse** risk. When G_loss collapses to ~0, G has fooled D completely and D is no longer a useful signal.

### Extending to Convolutional GAN (DCGAN)

For images larger than 32×32, replace the linear layers with transposed convolutions in G and strided convolutions in D:

```python
# Generator backbone for DCGAN (96×96 output)
class ConvGenerator(nn.Module):
    def __init__(self, latent_dim=100):
        super().__init__()
        self.project = nn.Linear(latent_dim, 512 * 6 * 6)
        self.conv = nn.Sequential(
            nn.ConvTranspose2d(512, 256, 4, 2, 1), nn.BatchNorm2d(256), nn.ReLU(),
            nn.ConvTranspose2d(256, 128, 4, 2, 1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.ConvTranspose2d(128,  64, 4, 2, 1), nn.BatchNorm2d(64),  nn.ReLU(),
            nn.ConvTranspose2d( 64,   3, 4, 2, 1), nn.Tanh(),
        )
    def forward(self, z):
        x = self.project(z).view(-1, 512, 6, 6)
        return self.conv(x)   # → (B, 3, 96, 96)
```

Key DCGAN guidelines: no pooling layers in D (use strided convolutions), no fully-connected hidden layers, BatchNorm in both networks (except D's input layer and G's output layer), LeakyReLU in D, ReLU in G.

---

## Use It

### GAN Variants and When to Reach for Each

| Variant | Key Idea | Best For |
|---|---|---|
| **Vanilla GAN** | Fully connected, BCE loss | Toy datasets, learning GAN mechanics |
| **DCGAN** | Convolutional architecture | Natural images up to ~128×128 |
| **WGAN / WGAN-GP** | Wasserstein distance + gradient penalty | Stable training, debugging mode collapse |
| **Conditional GAN (cGAN)** | Condition G and D on class label or embedding | Class-conditional generation, image-to-image |
| **Pix2Pix** | cGAN with paired image supervision + L1 loss | Day↔night, sketch→photo, satellite→map |
| **CycleGAN** | Dual GANs + cycle-consistency loss | Unpaired image translation (horse↔zebra) |
| **StyleGAN / StyleGAN2/3** | Style-based G with adaptive instance norm | High-resolution face synthesis, artistic control |
| **BigGAN** | Large-scale class-conditional GAN | ImageNet-scale generation |
| **GauGAN (SPADE)** | Semantic layout → photorealistic scene | Landscape synthesis from segmentation maps |

### Real-World Deployments

- **NVIDIA StyleGAN3** — used in [thispersondoesnotexist.com](https://thispersondoesnotexist.com) and synthetic dataset creation for face-recognition research.
- **Pix2Pix / CycleGAN** — Adobe Photoshop's Generative Fill pipeline borrows ideas from conditional GANs for content-aware fill and style transfer.
- **Medical imaging** — GANs generate synthetic CT/MRI scans to augment small labeled datasets for tumor detection and rare-disease classifiers.
- **Data augmentation pipelines** — teams plug DCGAN or StyleGAN outputs into training data to improve robustness of downstream classifiers.
- **Diffusion models have largely superseded GANs** for general image generation (better diversity, no mode collapse), but GANs remain preferred when inference latency matters — a single forward pass through G produces an image in milliseconds, whereas diffusion requires dozens of denoising steps.

---

## Common Pitfalls

- **Mode collapse:** G discovers one or a few outputs that consistently fool D and stops exploring. The generator "collapses" to producing identical or near-identical samples. Mitigation: use Wasserstein loss with gradient penalty (WGAN-GP), add minibatch discrimination, or use spectral normalization on D.

- **Discriminator winning too fast:** If D becomes too strong before G has learned anything, gradients flowing into G vanish (saturating sigmoid). Fix: reduce D's learning rate, add Gaussian noise to D's input, or apply label smoothing (use 0.9 instead of 1.0 for real labels).

- **Gradient vanishing due to D's sigmoid:** The original BCE loss is known to produce vanishing gradients when D is confident. Switch to the non-saturating loss (`-log D(G(z))` instead of `log(1 - D(G(z)))`) or to WGAN's Wasserstein distance.

- **Training instability / oscillation:** Loss values oscillate instead of converging. Common causes: mismatched learning rates between G and D, no batch normalization, or learning rates that are too high. Use Adam with `betas=(0.5, 0.999)` (not the default 0.9), and keep LR ≤ 2e-4.

- **Evaluating with raw loss values:** D_loss and G_loss are not reliable quality metrics — they measure the game score, not sample quality. Use Fréchet Inception Distance (FID) or Inception Score (IS) to measure actual output quality against a reference dataset.

---

## Exercises

1. **Easy — core mechanics:** Train the MNIST GAN from the Build It section for 20 epochs. After training, sample 25 images and visually identify which digits G learned to generate well versus poorly. Explain why some classes are easier to generate than others.

2. **Medium — conditional control:** Modify the vanilla GAN to a **Conditional GAN** by concatenating the one-hot class label to both G's input noise vector and D's input image. Train on MNIST and verify that passing label=7 reliably generates the digit 7. What happens when you interpolate between two class embeddings?

3. **Hard — stability investigation:** Implement a WGAN-GP on MNIST. Compare FID scores at epochs 10, 25, and 50 against the vanilla GAN. Document how the Wasserstein loss curve differs from BCE loss in terms of interpretability and correlation with visual quality. Write a one-page analysis of the trade-offs between training stability and compute cost.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Generator** | A network that "draws" images | A function mapping a random noise vector z to a synthetic sample; it never directly sees real data |
| **Discriminator** | A classifier that detects fakes | A binary classifier trained simultaneously with G; it also serves as G's only feedback signal — essentially G's loss function |
| **Latent space** | A hidden layer inside the network | The input space of the Generator (z-space); points in this space correspond to specific generated outputs, and linear paths produce smooth semantic transitions |
| **Mode collapse** | The GAN stopped learning | G has found a small set of outputs that consistently fool D and repeats them; diversity collapses even though individual samples look real |
| **Nash equilibrium** | The model converged | The theoretical fixed point where G perfectly replicates the data distribution and D outputs 0.5 everywhere; rarely achieved in practice but useful as a training target |
| **FID (Fréchet Inception Distance)** | A training metric | An evaluation metric computed on a held-out set: lower FID means generated images are statistically closer to real images in feature space |
| **WGAN-GP** | A GAN that uses gradient descent | Wasserstein GAN with Gradient Penalty: replaces BCE loss with the Wasserstein-1 distance and enforces the 1-Lipschitz constraint via a gradient penalty term, yielding more stable training |

---

## Further Reading

- **Original GAN paper — Goodfellow et al. (2014):** [https://arxiv.org/abs/1406.2661](https://arxiv.org/abs/1406.2661) — The foundational paper. Read Section 3 (Adversarial Nets) and Section 4 (Theoretical Results) for the minimax derivation.
- **DCGAN — Radford et al. (2015):** [https://arxiv.org/abs/1511.06434](https://arxiv.org/abs/1511.06434) — The paper that made GANs practical for image generation; introduces the convolutional architecture guidelines still used today.
- **WGAN-GP — Gulrajani et al. (2017):** [https://arxiv.org/abs/1704.00028](https://arxiv.org/abs/1704.00028) — The definitive fix for training instability; explains why BCE loss causes gradient issues and derives the Wasserstein alternative.
- **StyleGAN2 — Karras et al. (2020):** [https://arxiv.org/abs/1912.04958](https://arxiv.org/abs/1912.04958) — State-of-the-art GAN architecture for high-resolution synthesis; introduces weight demodulation and path-length regularization.
- **GAN Zoo (GitHub):** [https://github.com/hindupuravinash/the-gan-zoo](https://github.com/hindupuravinash/the-gan-zoo) — A curated catalog of 500+ GAN variants with paper links; useful for finding a specific GAN for a domain-specific problem.
