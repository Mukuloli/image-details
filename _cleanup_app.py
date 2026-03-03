"""
Clean up app.py:
1. Remove inline prompt definitions (now imported from prompts.py)
2. Remove upscale_image function and api_analyze_upscale route
"""
import os

with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Original app.py: {len(lines)} lines")

def find_line(lines, text, start=0):
    for i in range(start, len(lines)):
        if text in lines[i]:
            return i
    return -1

def find_triple_quote_end(lines, start):
    for i in range(start + 1, len(lines)):
        if '"""' in lines[i]:
            return i
    return -1

# Collect all ranges to remove (0-indexed start, 0-indexed end exclusive)
removals = []

# 1. VISION_PROMPT block
idx = find_line(lines, 'VISION_PROMPT = """You are an ELITE visual analyst')
if idx >= 0:
    end = find_triple_quote_end(lines, idx)
    # Include section comment lines above
    start = idx
    while start > 0 and ("---" in lines[start-1] or "Agentic Vision" in lines[start-1] or lines[start-1].strip() == ""):
        start -= 1
    removals.append((start, end + 1, "# VISION_PROMPT — imported from prompts.py\n\n"))
    print(f"  VISION_PROMPT: {end - start + 1} lines")

# 2. REFINEMENT_PROMPT block  
idx = find_line(lines, 'REFINEMENT_PROMPT = """You are an ELITE visual analyst reviewing')
if idx >= 0:
    end = find_triple_quote_end(lines, idx)
    removals.append((idx, end + 1, "# REFINEMENT_PROMPT — imported from prompts.py\n\n"))
    print(f"  REFINEMENT_PROMPT: {end - idx + 1} lines")

# 3. VERIFICATION_PROMPT block
idx = find_line(lines, 'VERIFICATION_PROMPT = """You are an ELITE clothing comparison')
if idx >= 0:
    end = find_triple_quote_end(lines, idx)
    # Include section comment
    start = idx
    while start > 0 and ("---" in lines[start-1] or "Agentic Verification" in lines[start-1] or lines[start-1].strip() == ""):
        start -= 1
    removals.append((start, end + 1, "\n# VERIFICATION_PROMPT — imported from prompts.py\n\n"))
    print(f"  VERIFICATION_PROMPT: {end - start + 1} lines")

# 4. GENERATION_SYSTEM_INSTRUCTION block
idx = find_line(lines, 'GENERATION_SYSTEM_INSTRUCTION = (')
if idx >= 0:
    end = idx
    for i in range(idx, len(lines)):
        if lines[i].strip() == ')':
            end = i
            break
    start = idx
    while start > 0 and ("---" in lines[start-1] or "System instruction" in lines[start-1] or lines[start-1].strip() == ""):
        start -= 1
    removals.append((start, end + 1, "\n# GENERATION_SYSTEM_INSTRUCTION — imported from prompts.py\n\n"))
    print(f"  GENERATION_SYSTEM_INSTRUCTION: {end - start + 1} lines")

# 5. VISION_EXTRACT_PROMPT block
idx = find_line(lines, 'VISION_EXTRACT_PROMPT = """Analyze this image')
if idx >= 0:
    end = find_triple_quote_end(lines, idx)
    # Include section comment above
    start = idx
    while start > 0 and ("---" in lines[start-1] or "Vision-First Pipeline" in lines[start-1] or lines[start-1].strip() == ""):
        start -= 1
    removals.append((start, end + 1, "\n# VISION_EXTRACT_PROMPT — imported from prompts.py\n\n"))
    print(f"  VISION_EXTRACT_PROMPT: {end - start + 1} lines")

# 6. upscale_image function
idx = find_line(lines, 'def upscale_image(image_bytes')
if idx >= 0:
    start = idx
    while start > 0 and ("---" in lines[start-1] or "Imagen" in lines[start-1] or "Upscale" in lines[start-1] or lines[start-1].strip() == ""):
        start -= 1
    # Find end of function
    end = idx + 1
    for i in range(idx + 1, len(lines)):
        s = lines[i].strip()
        if s.startswith("# ---") or (s.startswith("def ") and not lines[i].startswith(" ") and not lines[i].startswith("\t")):
            end = i
            break
    removals.append((start, end, ""))
    print(f"  upscale_image: {end - start} lines")

# 7. api_analyze_upscale route
idx = find_line(lines, 'def api_analyze_upscale')
if idx >= 0:
    # Back up to find @app.route
    start = idx
    for i in range(idx, max(idx - 5, 0), -1):
        if "@app.route" in lines[i]:
            start = i
            break
    # Include blank line before
    while start > 0 and lines[start-1].strip() == "":
        start -= 1
    # Find end of function
    end = idx + 1
    for i in range(idx + 1, len(lines)):
        s = lines[i].strip()
        if s.startswith("@app.route") or (s.startswith("def ") and not lines[i].startswith(" ") and not lines[i].startswith("\t")):
            end = i
            break
    removals.append((start, end, "\n"))
    print(f"  api_analyze_upscale: {end - start} lines")

# Apply removals in reverse order
removals.sort(key=lambda x: x[0], reverse=True)

total_removed = 0
for start, end, replacement in removals:
    removed = end - start
    total_removed += removed - (1 if replacement else 0)
    lines[start:end] = [replacement] if replacement else []

with open("app.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"\n✅ Cleaned app.py: {len(lines)} lines (removed ~{total_removed} lines)")
