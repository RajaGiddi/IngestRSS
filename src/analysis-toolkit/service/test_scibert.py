from __future__ import annotations
from typing import List, Dict, Tuple
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV

def unique_labels(labels: List[str]) -> List[str]:
    seen, out = set(), []
    for lbl in labels:
        if lbl not in seen:
            out.append(lbl); seen.add(lbl)
    return out

def top_k(d: Dict[str, float], k: int) -> List[Tuple[str, float]]:
    return sorted(d.items(), key=lambda x: -x[1])[:k]

# --------- demo data ---------
texts = [
    "We propose a new optimizer for deep neural networks and test it on ImageNet.",
    "The experiment confirms predictions of quantum electrodynamics in particle physics.",
    "We synthesized a new organic compound and studied its chemical reactions.",
    "A new model for reinforcement learning achieves state of the art on Atari games.",
    "We study the behavior of electrons in superconducting materials.",
]

label_pool = [
    # Computer Science
    "Artificial Intelligence",
    "Hardware Architecture",
    "Computational Complexity",
    "Computational Engineering, Finance, and Science",
    "Computational Geometry",
    "Computation and Language (Natural Language Processing)",
    "Cryptography and Security",
    "Computer Vision and Pattern Recognition",
    "Computers and Society",
    "Databases",
    "Distributed, Parallel, and Cluster Computing",
    "Digital Libraries",
    "Discrete Mathematics",
    "Data Structures and Algorithms",
    "Emerging Technologies",
    "Formal Languages and Automata Theory",
    "General Literature",
    "Graphics",
    "Game Theory in Computer Science",
    "Human-Computer Interaction",
    "Information Retrieval",
    "Information Theory",
    "Machine Learning",
    "Logic in Computer Science",
    "Multiagent Systems",
    "Multimedia",
    "Mathematical Software",
    "Numerical Analysis in Computer Science",
    "Neural and Evolutionary Computing",
    "Networking and Internet Architecture",
    "Other Computer Science",
    "Operating Systems",
    "Performance",
    "Programming Languages",
    "Robotics",
    "Symbolic Computation",
    "Sound",
    "Software Engineering",
    "Social and Information Networks",
    "Systems and Control",

    # Mathematics
    "Commutative Algebra",
    "Algebraic Geometry",
    "Analysis of Partial Differential Equations",
    "Algebraic Topology",
    "Classical Analysis and Ordinary Differential Equations",
    "Combinatorics",
    "Category Theory",
    "Complex Variables",
    "Differential Geometry",
    "Dynamical Systems",
    "Functional Analysis",
    "General Mathematics",
    "General Topology",
    "Group Theory",
    "Geometric Topology",
    "History and Overview of Mathematics",
    "Information Theory in Mathematics",
    "K-Theory and Homology",
    "Logic",
    "Metric Geometry",
    "Mathematical Physics",
    "Numerical Analysis",
    "Number Theory",
    "Operator Algebras",
    "Optimization and Control",
    "Probability",
    "Quantum Algebra",
    "Rings and Algebras",
    "Representation Theory",
    "Symplectic Geometry",
    "Spectral Theory",
    "Statistics Theory",

    # Physics
    "Accelerator Physics",
    "Atmospheric and Oceanic Physics",
    "Applied Physics",
    "Atomic and Molecular Clusters",
    "Atomic Physics",
    "Biological Physics",
    "Chemical Physics",
    "Classical Physics",
    "Computational Physics",
    "Data Analysis, Statistics, and Probability in Physics",
    "Physics Education",
    "Fluid Dynamics",
    "General Physics",
    "Geophysics",
    "History of Physics",
    "Instrumentation and Detectors",
    "Medical Physics",
    "Optics",
    "Plasma Physics",
    "Popular Physics",
    "Physics and Society",
    "Space Physics",

    # Astrophysics
    "Cosmology and Nongalactic Astrophysics",
    "Earth and Planetary Astrophysics",
    "Astrophysics of Galaxies",
    "High-Energy Astrophysical Phenomena",
    "Instrumentation and Methods for Astrophysics",
    "Solar and Stellar Astrophysics",

    # Condensed Matter
    "Disordered Systems and Neural Networks",
    "Mesoscale and Nanoscale Physics",
    "Materials Science",
    "Other Condensed Matter",
    "Quantum Gases",
    "Soft Condensed Matter",
    "Statistical Mechanics",
    "Strongly Correlated Electrons",
    "Superconductivity",

    # High Energy Physics
    "High Energy Physics - Experiment",
    "High Energy Physics - Lattice",
    "High Energy Physics - Phenomenology",
    "High Energy Physics - Theory",

    # Nuclear Physics
    "Nuclear Experiment",
    "Nuclear Theory",

    # General Relativity & Quantum Cosmology
    "General Relativity and Quantum Cosmology",

    # Quantum Physics
    "Quantum Physics",
    "Quantum Mechanics",
    "Quantum Computing",
    "Quantum Hardware",

    # Nonlinear Sciences
    "Adaptation and Self-Organizing Systems",
    "Chaotic Dynamics",
    "Cellular Automata and Lattice Gases",
    "Pattern Formation and Solitons",
    "Exactly Solvable and Integrable Systems",

    # Statistics
    "Applications (Statistics)",
    "Computation (Statistics)",
    "Methodology (Statistics)",
    "Machine Learning (Statistics)",
    "Other Statistics",
    "Statistics Theory",

    # Quantitative Biology
    "Biomolecules",
    "Cell Behavior",
    "Genomics",
    "Molecular Networks",
    "Neurons and Cognition",
    "Other Quantitative Biology",
    "Populations and Evolution",
    "Quantitative Methods",
    "Subcellular Processes",
    "Tissues and Organs",

    # Quantitative Finance
    "Computational Finance",
    "Economics",
    "General Quantitative Finance",
    "Mathematical Finance",
    "Portfolio Management",
    "Pricing of Securities",
    "Risk Management",
    "Statistical Finance",
    "Trading and Market Microstructure",

    # Electrical Engineering & Systems Science
    "Audio and Speech Processing",
    "Image and Video Processing",
    "Signal Processing",
    "Systems and Control (Engineering)",

    # Economics
    "Econometrics",
    "General Economics",
    "Theoretical Economics"
]

text_labels = [
    ["Machine Learning", "Artificial Intelligence"],
    ["Quantum Physics"],
    ["Chemical Physics", "Materials Science"],
    ["Artificial Intelligence", "Machine Learning", "Computer Vision and Pattern Recognition"],
    ["Superconductivity", "Materials Science"],
]

# --------- SciBERT embedder ---------
device = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained("allenai/scibert_scivocab_uncased")
model = AutoModel.from_pretrained("allenai/scibert_scivocab_uncased").to(device)
model.eval()

@torch.inference_mode()
def embed(batch_texts: List[str], batch_size: int = 16, max_len: int = 512) -> np.ndarray:
    vecs = []
    for i in range(0, len(batch_texts), batch_size):
        chunk = batch_texts[i:i+batch_size]
        inputs = tok(chunk, return_tensors="pt", truncation=True, padding=True, max_length=max_len).to(device)
        out = model(**inputs).last_hidden_state
        emb = out.mean(dim=1).cpu().numpy()
        vecs.append(emb)
    X = np.vstack(vecs)
    X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)  # L2 normalize
    return X

# --------- prepare labels ---------
label_pool_unique = unique_labels(label_pool)
mlb = MultiLabelBinarizer(classes=label_pool_unique)
Y_full = mlb.fit_transform(text_labels)                # (N, C_pool)
pos_mask = (Y_full.sum(axis=0) > 0)                    # keep only classes that appear
active_labels = np.array(label_pool_unique)[pos_mask].tolist()
Y = Y_full[:, pos_mask]
if Y.shape[1] == 0:
    raise ValueError("No active classes; add labeled data.")

X = embed(texts)

# --------- SAFE, ADAPTIVE CALIBRATED OVR ---------
class SafeCalibratedOvR:
    """
    Per-class binary models with *adaptive* calibration:
    - If a class has both positives and negatives:
        * If min(n_pos, n_neg) >= 2: calibrate with cv = min(3, n_pos, n_neg)
        * Else: fit uncalibrated LogisticRegression
    - If a class is all one label: mark as untrainable -> probs=0.0
    """
    def __init__(self, base_factory):
        self.base_factory = base_factory
        self.estims_ = []          # list[Union[CalibratedClassifierCV, LogisticRegression, None]]
        self.classes_: List[str] = []

    def fit(self, X: np.ndarray, Y: np.ndarray, classes: List[str]):
        self.classes_ = classes
        self.estims_.clear()
        C = Y.shape[1]
        for j in range(C):
            yj = Y[:, j]
            n_pos = int(yj.sum())
            n_neg = int((1 - yj).sum())
            if n_pos == 0 or n_neg == 0:
                self.estims_.append(None)
                continue
            min_class = min(n_pos, n_neg)
            if min_class >= 2:  # can at least do 2-fold; choose cv <= min(3, n_pos, n_neg)
                cv = min(3, n_pos, n_neg)
                base = self.base_factory()
                clf = CalibratedClassifierCV(base, method="sigmoid", cv=cv)
                clf.fit(X, yj)
                self.estims_.append(clf)
            else:
                # too few positives/negatives to calibrate; fit uncalibrated LR
                base = self.base_factory()
                base.fit(X, yj)
                self.estims_.append(base)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        probs = []
        for est in self.estims_:
            if est is None:
                probs.append(np.zeros(X.shape[0]))
            else:
                p = est.predict_proba(X)
                p = p[:, 1] if p.ndim == 2 else p 
                probs.append(p)
        return np.vstack(probs).T 

def base_lr():
    return LogisticRegression(max_iter=3000, class_weight="balanced", solver="lbfgs")

covr = SafeCalibratedOvR(base_lr).fit(X, Y, active_labels)

# --------- inference ---------
GLOBAL_THRESHOLD = 0.30

def probs_for_all(text: str) -> Dict[str, float]:
    emb = embed([text])
    p_active = covr.predict_proba(emb)[0]
    amap = dict(zip(active_labels, p_active))
    return {lbl: float(amap.get(lbl, 0.0)) for lbl in label_pool_unique}

def predict_labels(text: str, threshold: float = GLOBAL_THRESHOLD, topk: int | None = 3):
    probs = probs_for_all(text)
    picked = [(l, p) for l, p in probs.items() if p >= threshold]
    picked.sort(key=lambda x: -x[1])
    if not picked and topk:
        picked = top_k(probs, topk)
    return picked

if __name__ == "__main__":
    new_text = "This paper introduces a novel method for simulating molecules using quantum computers."
    full = probs_for_all(new_text)
    print("Top scores:", top_k(full, 10))
    print("Thresholded:", predict_labels(new_text))
