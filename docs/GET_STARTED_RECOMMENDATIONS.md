# Quick Start: Cost-Saving Recommendations

## What's New

Your `collector.sh` script now automatically fetches cost-saving recommendations from Oracle Cloud Advisor!

## One-Minute Overview

- **Automatic**: Runs without any changes to your command
- **Output**: Saved to `output/recommendations.out` 
- **Format**: JSON with actionable cost-saving recommendations
- **Benefit**: Get specific ways to reduce your OCI costs

## Run It

```bash
./collector.sh ocid1.tenancy.oc1..aaaaa us-ashburn-1 2025-11-01 2025-11-20
```

That's it! The recommendations file is generated automatically.

## View Results

### Quick preview
```bash
head -100 output/recommendations.out
```

### See summary
```bash
python3 -c "
import json
data = json.load(open('output/recommendations.out'))
print(f'Total Recommendations: {len(data[\"items\"])}')
"
```

### Export to CSV
```bash
python3 -c "
import json, pandas as pd
data = json.load(open('output/recommendations.out'))
df = pd.DataFrame(data['items'])
df.to_csv('recommendations.csv', index=False)
print('✅ Exported to recommendations.csv')
"
```

## Key Files

| File | Purpose |
|------|---------|
| `output/recommendations.out` | **Your recommendations (NEW)** |
| `output/output_merged.csv` | Cost data |
| `docs/RECOMMENDATIONS.md` | Complete guide |
| `docs/RECOMMENDATIONS_QUICK_REFERENCE.md` | Examples & troubleshooting |

## Common Questions

**Q: What if I don't see any recommendations?**  
A: Cloud Advisor needs 24-48 hours to analyze your environment initially.

**Q: Will this slow down the collection?**  
A: Only adds ~2-10 seconds to the total runtime.

**Q: What if I get an error?**  
A: Check that your OCI user has the right permissions:
```
ALLOW {group} to read optimizer-recommendations IN TENANCY
```

**Q: How do I use the recommendations?**  
See `docs/RECOMMENDATIONS_QUICK_REFERENCE.md` for Python examples to:
- Filter by category
- Calculate total savings
- Export to CSV
- Find critical recommendations

## Next Steps

1. ✅ Run the collector (recommendations will be fetched automatically)
2. 📖 Review `output/recommendations.out`
3. 📊 Analyze using provided Python examples
4. 💰 Implement recommendations to save costs

## Need Help?

- **Quick Reference**: `docs/RECOMMENDATIONS_QUICK_REFERENCE.md`
- **Complete Guide**: `docs/RECOMMENDATIONS.md`
- **Technical Details**: `IMPLEMENTATION_SUMMARY.md`
- **General Help**: `README.md`

---

**That's all!** Your collector now gathers both cost data and cost-saving recommendations automatically. 🎉
