from typing import List

DEFAULT_TAG_KEYWORDS = {
    'Artificial Intelligence': ['ai', 'artificial intelligence', 'neural network', 'deep learning', 'transformer', 'llm', 'gpt'],
    'Machine Learning': ['machine learning', 'ml', 'supervised', 'unsupervised', 'reinforcement learning', 'gradient boosting', 'svm'],
    'Computer Vision and Pattern Recognition': ['computer vision', 'image', 'video', 'segmentation', 'detection', 'recognition', 'pose', 'object'],
    'Mathematics': ['theorem', 'algebra', 'geometry', 'topology', 'calculus', 'proof', 'combinatorics'],
    'Physics': ['physics', 'quantum', 'particle', 'astrophysics', 'cosmology', 'relativity', 'thermodynamics'],
    'Quantum Physics': ['quantum', 'qubit', 'entanglement', 'superposition'],
    'Superconductivity': ['superconduct', 'meissner', 'cooper pair', 'bcs'],
    'Chemical Physics': ['chemical', 'molecule', 'spectroscopy', 'chemistry', 'reaction'],
    'Materials Science': ['material', 'crystal', 'lattice', 'semiconductor', 'polymer', 'alloy', 'thin film'],
    'Biology': ['biology', 'genome', 'cell', 'protein', 'rna', 'dna', 'enzyme'],
    'Mechanical Engineering': ['mechanical', 'fluid', 'turbulence', 'thermo', 'stress', 'strain', 'mechanics', 'vibration']
}


def label_article(text: str, max_labels: int = 5) -> List[str]:
    if not text:
        return []
    t = text.lower()
    scores = []
    for label, kws in DEFAULT_TAG_KEYWORDS.items():
        score = 0
        for kw in kws:
            if kw in t:
                # weight by keyword length to mildly reward specificity
                score += max(len(kw) // 4, 1)
        if score > 0:
            scores.append((label, score))
    scores.sort(key=lambda x: -x[1])
    return [lbl for lbl, _ in scores[:max_labels]]
