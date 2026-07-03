import json
import math
from pathlib import Path

def main():
    repo_dir = Path(__file__).resolve().parent
    metadata_path = repo_dir / "results_metadata_with_sp.json"
    
    with open(metadata_path, "r") as f:
        data = json.load(f)
        
    stats = {}
    for row in data:
        key = f"{row['model_name']} | {row['framework']}"
        if key not in stats:
            stats[key] = []
        stats[key].append(row.get('sm', 0))
        
    print("=" * 60)
    print(f"{'Model | Framework':<40} | {'SM Score':<6} | {'SD':<6} | {'90% CI'}")
    print("=" * 60)
    
    results = []
    for key, scores in stats.items():
        n = len(scores)
        if n == 0:
            continue
        avg = sum(scores) / n
        variance = sum((x - avg) ** 2 for x in scores) / (n - 1 if n > 1 else 1)
        sd = math.sqrt(variance)
        
        # 90% Confidence Interval
        # alpha = 0.1, z = 1.645
        z = 1.645
        margin = z * (sd / math.sqrt(n))
        
        results.append((avg, key, sd, margin))
        
    results.sort(key=lambda x: x[0], reverse=True)
    
    for avg, key, sd, margin in results:
        print(f"{key:<40} | {(avg*100):.1f}%  | {sd:.3f} | ± {(margin*100):.2f}%")
        
    print("=" * 60)
    print("Metrics successfully computed from results_metadata_with_sp.json.")

if __name__ == "__main__":
    main()
