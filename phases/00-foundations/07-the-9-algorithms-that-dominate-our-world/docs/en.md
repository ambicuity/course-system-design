# The 9 Algorithms That Dominate Our World

> Nine algorithms that quietly run the modern world — from search engines and GPS to encryption and machine learning. Know what they do and why they matter.

**Type:** Learn
**Prerequisites:** Basic programming, comfort with math notation
**Time:** ~25 minutes

---

## The Problem

Most software engineers use algorithms every day without naming them. They sort lists, search for items, find shortest paths, compress data, encrypt messages. The difference between a senior engineer and a junior is often not "knows more algorithms" but "knows which algorithms are running under the hood, why they were chosen, and what their trade-offs are."

Every system you build sits on top of a handful of foundational algorithms. Search engines use link analysis and sorting. Maps use shortest-path algorithms. Networks use cryptography and hashing. Machine learning is built on transformers and gradient descent. Compression is everywhere.

This lesson walks through nine algorithms that come up constantly in real systems. For each, you get the problem it solves, the core idea, where it shows up, and when it matters.

---

## The Concept

### The nine algorithms at a glance

```
   1. Sorting                  — ordering data
   2. Dijkstra's algorithm    — shortest path on a graph
   3. Transformers            — attention-based learning
   4. Link Analysis (PageRank)— ranking by connections
   5. RSA                     — public-key encryption
   6. Integer Factorization   — the basis of RSA security
   7. Convolutional Neural Networks — image and signal processing
   8. Huffman Coding          — data compression
   9. Secure Hash Algorithm   — fingerprints and integrity
```

These nine power search engines, social networks, WiFi, cell phones, encryption, banking, satellites, and modern AI. Most engineers will never implement them from scratch — but every senior engineer should know what they do.

---

### 1. Sorting

**Problem:** given a collection of items, arrange them in a defined order.

**Core idea:** compare and rearrange. The variations differ in time complexity, stability, memory usage, and adaptability.

| Algorithm | Best for | Time | Space | Stable? |
|---|---|---|---|---|
| Bubble sort | Teaching only | O(n²) | O(1) | Yes |
| Insertion sort | Nearly-sorted data | O(n) best | O(1) | Yes |
| Merge sort | General purpose, stable | O(n log n) | O(n) | Yes |
| Quick sort | General purpose, in-place | O(n log n) avg | O(log n) | No |
| Heap sort | In-place, worst-case guarantee | O(n log n) | O(1) | No |
| Timsort | Real-world data | O(n log n) | O(n) | Yes |

**Where it shows up:**

- Database query results (ORDER BY)
- File system listings (sorted directory)
- Search indexing (sorted inverted indexes)
- Any UI that displays lists (sorted feeds, sorted tables)

**Why it matters:** sorting is a prerequisite for binary search, merge operations, deduplication, and many other algorithms. The choice of sorting algorithm affects performance significantly on real-world data, which is why Python and Java use Timsort (a hybrid of merge sort and insertion sort optimized for real data).

---

### 2. Dijkstra's Algorithm

**Problem:** given a graph with weighted edges, find the shortest path from a source node to all others.

**Core idea:** maintain a set of unvisited nodes; repeatedly pick the unvisited node with the smallest known distance; update the distances of its neighbors.

```
   Graph:                Distances from A:
       A                A: 0
      / \               B: 4  (via A)
   1 /   \ 2            C: 3  (via A)
    /     \             D: 6  (via A → B → D, or A → C → D)
   B---3---C
    \     /
   4 \   / 5
      \ /
       D
```

**Properties:**

- Works on graphs with non-negative weights
- Time complexity: O((V + E) log V) with a priority queue
- Finds the shortest path, not just *a* path
- Does NOT work with negative edge weights (use Bellman-Ford instead)

**Where it shows up:**

- GPS navigation (shortest route)
- Network routing (OSPF, IS-IS)
- Game AI (pathfinding)
- Operations research (logistics, supply chains)

**Modern variants:** A* search adds heuristics for faster pathfinding; bidirectional Dijkstra searches from both ends.

---

### 3. Transformers

**Problem:** process sequences (text, code, time series, images) with attention to relationships between elements regardless of distance.

**Core idea:** every element in the sequence attends to every other element, learning which relationships matter. The "attention" mechanism is the heart of the architecture.

```
   Input:  "The cat sat on the mat"

   Self-attention:
     "The"   attends to all 6 tokens (with weights)
     "cat"   attends to all 6 tokens (with weights)
     "sat"   attends to all 6 tokens (with weights)
     ...
     Each token's output = weighted sum of all tokens
```

**Properties:**

- Parallelizable (unlike RNNs which are sequential)
- Handles long-range dependencies (unlike CNNs which have local receptive fields)
- Scales with data and compute (scaling laws)
- The foundation of every modern LLM (GPT, Claude, Llama, Gemini)

**Where it shows up:**

- Large language models (text generation, summarization, Q&A)
- Machine translation
- Code generation
- Image classification (Vision Transformer)
- Speech recognition and synthesis
- Time-series forecasting
- Protein structure prediction (AlphaFold)

**Why it matters:** transformers are the single most important algorithmic innovation of the 2010s for AI. Almost every state-of-the-art model in language, vision, audio, and multimodal tasks is transformer-based.

---

### 4. Link Analysis (PageRank)

**Problem:** given a graph of links between pages (or people, papers, products), rank them by importance.

**Core idea:** a page is important if it is linked to by other important pages. Iteratively compute importance scores until they converge.

```
   Web graph:                PageRank scores (initial):
       A ──► B                  A: 1
       │     │                  B: 1
       ▼     ▼                  C: 1
       C ◄── D                  D: 1

   After iteration:
     A: 0.15  (linked by no one)
     B: 0.30  (linked by A)
     C: 0.45  (linked by A, B, D)
     D: 0.15  (linked by B)
```

**Properties:**

- Treats a link as a "vote" of importance
- Handles the "random surfer" model (a person clicking links occasionally jumps to a random page)
- Resistant to spam (a page can vote for itself, but it counts once)
- Time complexity: O(iterations × edges), converges quickly in practice

**Where it shows up:**

- Google Search ranking (the original PageRank)
- Citation analysis in academic papers
- Social network influence ranking
- Recommendation systems
- Knowledge graph entity ranking

**Modern variants:** personalized PageRank, Topic-Sensitive PageRank, TrustRank.

---

### 5. RSA Algorithm

**Problem:** enable secure communication between two parties who have never met, without a pre-shared secret.

**Core idea:** encryption and decryption use different keys. The encryption key can be public; the decryption key is private. Security rests on the difficulty of factoring large numbers.

```
   Public key (e, n):    shared openly
   Private key (d, n):   kept secret

   Encrypt:    c = m^e mod n
   Decrypt:    m = c^d mod n

   Knowing (e, n) does not reveal d (without factoring n)
```

**Properties:**

- Asymmetric: encrypt with one key, decrypt with the other
- Used for encryption, digital signatures, and key exchange
- Practical key sizes: 2048 or 4096 bits
- Much slower than symmetric encryption (AES) — typically used to exchange a symmetric key, then AES does the bulk encryption

**Where it shows up:**

- HTTPS (TLS handshake)
- SSH authentication
- Digital signatures (verify a document was signed by the holder of a private key)
- Email encryption (PGP, S/MIME)
- Cryptocurrency wallets
- Code signing

**Why it matters:** RSA is the foundation of public-key cryptography on the internet. Every secure connection begins with RSA (or its successor, elliptic-curve cryptography) to exchange a session key.

---

### 6. Integer Factorization

**Problem:** given a large number, find its prime factors.

**Core idea:** trial division for small numbers; sophisticated algorithms for large numbers (Pollard's rho, quadratic sieve, general number field sieve).

```
   15 = 3 × 5
   91 = 7 × 13
   360 = 2³ × 3² × 5
   RSA-2048 = ?? × ?? (would take the age of the universe with current methods)
```

**Properties:**

- Easy to multiply two primes to get a number
- Hard to factor a number back into primes (no known polynomial-time algorithm on a classical computer)
- The security of RSA depends on this asymmetry
- Shor's algorithm (on a quantum computer) can factor in polynomial time — which is why post-quantum cryptography is being developed

**Where it shows up:**

- RSA security (the basis of all RSA key sizes)
- Cryptographic protocol design (key sizes are chosen based on factorization difficulty)
- Post-quantum cryptography research (replacing RSA before quantum computers break it)

**Why it matters:** integer factorization is the computational hardness assumption that protects most internet security. If a fast algorithm were found, RSA would be broken overnight.

---

### 7. Convolutional Neural Networks (CNNs)

**Problem:** process images (and signals) efficiently, recognizing patterns regardless of position.

**Core idea:** small filters (kernels) slide across the image, detecting local patterns. Deeper layers detect more complex patterns.

```
   Input image (28×28)
        │
        ▼
   Conv layer: 16 filters, 3×3 → 16 feature maps (26×26)
        │   learns: edges, gradients
        ▼
   Pool layer: downsample → 16 feature maps (13×13)
        │
        ▼
   Conv layer: 32 filters → 32 feature maps (11×11)
        │   learns: textures, shapes
        ▼
   Pool layer: downsample → 32 feature maps (5×5)
        │
        ▼
   Fully connected → 10 class probabilities
```

**Properties:**

- Exploits spatial locality (nearby pixels are related)
- Translation-invariant (a cat in the corner is detected the same as in the center)
- Hierarchical features (edges → textures → parts → objects)
- Far fewer parameters than fully-connected networks

**Where it shows up:**

- Image classification, object detection, segmentation
- Facial recognition
- Medical imaging (tumor detection)
- Self-driving cars (lane detection, pedestrian detection)
- Video analysis
- Audio processing (spectrograms)

**Modern note:** Vision Transformers (ViT) have replaced CNNs in many image tasks. The two architectures coexist; CNNs are more efficient for small data, transformers for large data.

---

### 8. Huffman Coding

**Problem:** compress data (text, files, images) to use fewer bits without losing information.

**Core idea:** assign shorter codes to more frequent symbols, longer codes to less frequent ones. The resulting encoding is optimal for the given symbol frequencies.

```
   Symbol frequencies in "ABRACADABRA":
     A: 5  (most frequent → shortest code: 0)
     B: 2
     R: 2
     C: 1  (least frequent → longest code: 1100)

   Huffman tree:
              (*)
             /   \
           (A,0)  (*)
                  / \
                 (B)  (*)
                     / \
                  (R)   (*)
                       /   \
                    (C)   (D)
```

**Properties:**

- Lossless compression (original data fully recoverable)
- Optimal prefix code given symbol frequencies
- Used as a component in many compression algorithms (DEFLATE, JPEG, MP3)
- Two-pass: build frequency table, then build tree and encode

**Where it shows up:**

- DEFLATE (zip, gzip, PNG)
- JPEG (image compression)
- MP3 (audio compression)
- PKZIP
- HTTP/2 HPACK header compression

**Why it matters:** Huffman coding is the building block of most lossless compression. It is taught in every algorithms course for a reason — it is both elegant and ubiquitous.

---

### 9. Secure Hash Algorithm (SHA)

**Problem:** produce a fixed-length "fingerprint" of any input data, with the property that small changes in the input produce completely different fingerprints, and you cannot reverse the fingerprint to recover the input.

**Core idea:** repeatedly apply a one-way compression function to the input, producing a fixed-length output. SHA-256 produces 256-bit outputs.

```
   Input:    "Hello, world!"
   SHA-256:  315f5bdb76d078c43b8ac0064e4a0164612b1fce77c869345bfc94c75894edd3

   Input:    "Hello, world?"
   SHA-256:  6f86c66d5f4c0b3a0b2a6b3e1b9c2a6f1c4d5e8a3b6c9d0e2f4a5b6c7d8e9f0a

   (completely different, even though only one character changed)
```

**Properties:**

- **Deterministic** — same input always produces same output
- **Fast** — easy to compute
- **Avalanche** — tiny input change → completely different output
- **One-way** — cannot reverse to find input
- **Collision-resistant** — hard to find two inputs with the same hash

**Where it shows up:**

- Password storage (hash + salt, not plain hash)
- File integrity verification (checksums, git commit hashes)
- Digital signatures (sign the hash, not the data)
- Blockchain (each block hashes the previous)
- TLS certificates (signed by CA)
- Content-addressed storage (S3 by hash, IPFS, git)
- HMAC for authenticated messages

**Hash families:**

- **MD5** — broken, do not use for security
- **SHA-1** — deprecated for security
- **SHA-2** (SHA-256, SHA-512) — current standard
- **SHA-3** — alternative construction
- **BLAKE2 / BLAKE3** — faster, increasingly popular

---

## Build It / In Depth

### How the algorithms compose in real systems

```
   Your web request
       │
       ▼
   [TLS] uses RSA / ECDH to exchange keys         ← Algorithm 5
       │
       ▼
   [HTTPS] encrypts with AES                      ← (not in our 9, but uses #5)
       │
       ▼
   [CDN] routes to nearest edge by routing tables
       │
       ▼
   [Load balancer] uses consistent hashing       ← Algorithm 9 for key distribution
       │
       ▼
   [Search] ranks results by PageRank            ← Algorithm 4
       │
       ▼
   [Database] sorts results                       ← Algorithm 1
       │
       ▼
   [Recommendation] uses transformers to rank     ← Algorithm 3
       │
       ▼
   [Image search] uses CNN for visual features    ← Algorithm 7
       │
       ▼
   [Storage] uses SHA-256 for content addressing ← Algorithm 9
       │
       ▼
   [Compression] uses Huffman coding for images   ← Algorithm 8
```

A single web request can touch six of the nine algorithms. Every modern system is a composition.

---

### Which algorithms to know in depth

| Algorithm | When to study it deeply |
|---|---|
| Sorting | Always — implement merge sort and quicksort at least once |
| Dijkstra | When working with graphs, routing, or pathfinding |
| Transformers | If you build AI applications |
| PageRank | When working on recommendation or search systems |
| RSA | If you work in security, cryptography, or blockchain |
| Integer factorization | Rarely — know the security implication, not the algorithm |
| CNNs | If you work on computer vision |
| Huffman coding | When implementing compression or file formats |
| SHA | If you work in security, integrity, or content addressing |

---

## Common Pitfalls

- **"Just use a library."** True for most code, but you should still know what the library does. Knowing the algorithm makes you a better engineer at debugging, optimization, and design.

- **Choosing an algorithm without knowing the problem.** Quick sort is fast on average but slow on already-sorted data. SHA-256 is appropriate for password hashing is a common misconception (use bcrypt or Argon2). Always match the algorithm to the problem.

- **Ignoring the security context.** MD5 is broken for cryptographic use but fine for non-security checksums. RSA is appropriate for small data but not for encrypting large files. Algorithm choice depends on the threat model.

- **Confusing the algorithm with its application.** "We use a transformer" can mean GPT, BERT, ViT, or Whisper — different applications of the same architectural idea.

- **Blaming the algorithm for misuse.** Most "algorithm failures" are operator failures — wrong parameters, wrong data, wrong assumptions.

- **Optimizing prematurely.** The fastest algorithm is the one you have when you need it. Most production systems use general-purpose algorithms (Timsort, SHA-256) because they handle real-world data well.

---

## Exercises

1. **Easy** — Pick three of the nine algorithms. For each, describe the problem it solves in one sentence and a real system that uses it.

2. **Medium** — Take a real product you use daily (Google Search, Google Maps, Instagram, WhatsApp). Identify which five of the nine algorithms it likely uses. For each, explain how.

3. **Hard** — Design a system for a video streaming platform. Pick which five of the nine algorithms you would rely on most heavily. Justify each choice with the specific problem it solves.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Algorithm | A code recipe | A precise, finite sequence of well-defined instructions that solves a problem |
| Time complexity | Speed | How the algorithm's running time scales with input size (O(n), O(n log n), O(n²)) |
| Space complexity | Memory usage | How the algorithm's memory usage scales with input size |
| Stable sort | A sort that preserves order | A sort where equal elements maintain their relative order (important for multi-key sorts) |
| Public-key cryptography | Asymmetric encryption | A cryptosystem where encryption and decryption use different keys, enabling secure communication without a pre-shared secret |
| Hash function | A fingerprint | A function that maps arbitrary input to a fixed-size output, designed to be one-way and collision-resistant |
| Attention | A type of lookup | A mechanism that computes weighted relationships between elements in a sequence; the core of transformers |
| Convolutional layer | Image processing | A neural network layer that applies learned filters to local regions of the input; the building block of CNNs |

---

## Further Reading

- **"Introduction to Algorithms" (CLRS)** — the canonical algorithms textbook: https://mitpress.mit.edu/9780262033848/
- **"Designing Data-Intensive Applications"** — Martin Kleppmann; covers the algorithms underlying real systems: https://dataintensive.net/
- **"Attention Is All You Need"** — the original transformer paper: https://arxiv.org/abs/1706.03762
- **"PageRank"** — the original Google paper: https://web.archive.org/web/20070604071759/http://www-db.stanford.edu/~backrub/google.html
- **"A Few Useful Things to Know About Machine Learning"** — Pedro Domingos; pragmatic intro to ML algorithms: https://homes.cs.washington.edu/~pedrod/papers/cacm12.pdf