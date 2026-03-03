import os
import json
import base64
import io
import re
import traceback

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from google import genai
from google.genai import types
from PIL import Image
from prompts import (
    VISION_PROMPT,
    REFINEMENT_PROMPT,
    VERIFICATION_PROMPT,
    GENERATION_SYSTEM_INSTRUCTION,
    VISION_EXTRACT_PROMPT,
)

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- Safe Gemini client initialization ---
_api_key = os.getenv("GEMINI_API_KEY")
client = None
if _api_key:
    try:
        client = genai.Client(api_key=_api_key)
        print(f"[INIT] Gemini client initialized successfully.")
    except Exception as e:
        print(f"[INIT] WARNING: Failed to initialize Gemini client: {e}")
else:
    print("[INIT] WARNING: GEMINI_API_KEY not set. API routes will not work.")

# ---------------------------------------------------------------------------
# Agentic Vision Module — Extracts structured details from an image
# ---------------------------------------------------------------------------
# VISION_PROMPT — imported from prompts.py



def _parse_json_response(raw_text: str) -> dict:
    """Parse JSON from model response, stripping markdown fences if present."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
    return json.loads(raw_text)


# REFINEMENT_PROMPT — imported from prompts.py



def _deep_merge(base: dict, updates: dict) -> dict:
    """Deep merge updates into base. For jewelry_pieces, append new entries."""
    merged = dict(base)
    for key, val in updates.items():
        if val is None or (isinstance(val, str) and val.lower() in ("null", "none", "")):
            continue  # Skip empty updates
        if key == "jewelry_pieces" and isinstance(val, list) and isinstance(merged.get(key), list):
            # Merge jewelry: add new pieces, update existing by type
            existing_types = {p.get("type", "").lower() for p in merged[key] if isinstance(p, dict)}
            for piece in val:
                if isinstance(piece, dict):
                    ptype = piece.get("type", "").lower()
                    if ptype and ptype not in existing_types:
                        merged[key].append(piece)
                        existing_types.add(ptype)
                    elif ptype:
                        # Update existing piece with richer details
                        for i, existing in enumerate(merged[key]):
                            if isinstance(existing, dict) and existing.get("type", "").lower() == ptype:
                                for pk, pv in piece.items():
                                    if pv and str(pv).lower() not in ("null", "none", ""):
                                        existing_len = len(str(existing.get(pk, "")))
                                        update_len = len(str(pv))
                                        if update_len > existing_len:
                                            existing[pk] = pv
                                break
        elif isinstance(val, str) and isinstance(merged.get(key), str):
            # Keep the longer/more detailed string
            if len(val) > len(merged.get(key, "")):
                merged[key] = val
        elif isinstance(val, list) and isinstance(merged.get(key), list):
            # For other arrays, keep longer one
            if len(val) > len(merged.get(key, [])):
                merged[key] = val
        else:
            # New field or direct replacement
            if key not in merged or merged[key] is None:
                merged[key] = val
            elif isinstance(val, str) and len(val) > len(str(merged.get(key, ""))):
                merged[key] = val
            elif not isinstance(val, str):
                merged[key] = val
    return merged


def analyze_image(image_bytes: bytes, mime_type: str) -> dict:
    """Agentic multi-pass analysis with ZOOM-FOCUS for 100% detail capture.
    
    Pass 1: Full analysis — extract all dress & jewelry details.
    Pass 2: Self-review — look at image again, find gaps, fill them in.
    Pass 3: ZOOM-FOCUS on CLOTHING — zoom into embroidery, borders, fabric, neckline, sleeves.
    Pass 4: ZOOM-FOCUS on JEWELRY — zoom into each piece, verify stone colors.
    Result: Deep merge of all passes for maximum detail.
    """
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    # ─── Pass 1: Full analysis ───
    print("[VISION] Pass 1/4: Full image analysis (gemini-3-flash-preview)...")
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[image_part, VISION_PROMPT],
        config=types.GenerateContentConfig(
            temperature=0.2,
        ),
    )
    first_pass = _parse_json_response(response.text)
    print(f"[VISION] Pass 1 complete. Got {len(first_pass)} fields.")

    # ─── Pass 2: Self-review — find gaps & missing details ───
    print("[VISION] Pass 2/4: Self-reviewing for missed details...")
    refinement_text = REFINEMENT_PROMPT.replace(
        "{first_pass_json}", json.dumps(first_pass, indent=2, ensure_ascii=False)
    ).replace(
        "{latkan_value}", first_pass.get("latkan_tassels", "not specified")
    )
    try:
        refine_response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[image_part, refinement_text],
            config=types.GenerateContentConfig(
                temperature=0.15,
            ),
        )
        second_pass = _parse_json_response(refine_response.text)
        updates_count = len(second_pass)
        print(f"[VISION] Pass 2 complete. Found {updates_count} updates/additions.")
        result = _deep_merge(first_pass, second_pass)
    except Exception as e:
        print(f"[VISION] ⚠️ Pass 2 failed ({e}), using Pass 1 result only.")
        result = first_pass

    # ─── Pass 3: ZOOM-FOCUS on CLOTHING DETAILS ───
    print("[VISION] Pass 3/4: ZOOM-FOCUS on clothing details...")
    clothing_zoom_prompt = f"""You are zooming into this image to verify CLOTHING details.
The current analysis says:
- Dress type: {result.get('dress_type', 'unknown')}
- Primary color: {result.get('primary_color', 'unknown')}
- Primary color HEX: {result.get('primary_color_hex', 'unknown')}
- Neckline: {result.get('neckline', 'unknown')}
- Embroidery: {str(result.get('embroidery', 'unknown'))[:200]}
- Border: {str(result.get('border_design', 'unknown'))[:200]}
- Latkans: {result.get('latkan_tassels', 'unknown')}

NOW ZOOM INTO THE IMAGE and verify/correct each clothing area:

0. **🚨 PRIMARY COLOR VERIFICATION (MOST CRITICAL — DO THIS FIRST)** — 
   Look at the LARGEST flat area of the dress fabric (no embroidery, no shadow).
   The current analysis says the color is: "{result.get('primary_color', 'unknown')}" ({result.get('primary_color_hex', '?')})
   - Is this EXACTLY right? Or is it slightly different?
   - Common mistakes: calling fuchsia "pink", calling magenta "red", calling teal "blue"
   - If the color is even SLIGHTLY wrong, provide the CORRECTED color name + HEX code
   - The HEX must match what your eyes see in the actual image pixels

1. **NECKLINE** — Zoom in to the neckline area. Is the current description accurate? What is the EXACT shape (V-neck, sweetheart, round, boat, square, scalloped)? What embellishment is on the neckline edge?

2. **EMBROIDERY ZONES** — Zoom into EACH embroidery zone separately:
   - BODICE embroidery: What EXACT motifs (floral, paisley, geometric, vine)? How dense? What threads (zari, sequin, resham)?
   - SKIRT embroidery: Same questions. Is it all-over or in panels/zones?
   - SLEEVE embroidery: What design? Dense or sparse?
   - WAISTBAND: Is there a decorative waistband between bodice and skirt?

3. **BORDERS** — Zoom into ALL borders:
   - HEMLINE border: Width in cm, design pattern, colors, straight or scalloped edge?
   - SLEEVE border: Same details
   - DUPATTA border: Same details
   - Are the borders SAME on all pieces or DIFFERENT?

4. **FABRIC TEXTURE** — Zoom into the base fabric between embroidery:
   - Is there a micro-pattern or booti (small repeated motifs)?
   - What is the fabric weave (silk, georgette, net, velvet)?

5. **LATKANS/TASSELS** — Zoom into any tassels on the waist/drawstring:
   - EXACT count, size (small/medium/large), material, colors, hanging length

Return ONLY a JSON object with corrections/additions. For UNCHANGED fields, omit them.
Output format:
```json
{{
  "primary_color": "CORRECTED exact shade name + hex if the current one is wrong",
  "primary_color_hex": "#CORRECTED_HEX if wrong",
  "neckline": "corrected description if different",
  "embroidery": "corrected/enhanced description",
  "border_design": "corrected/enhanced description",
  "latkan_tassels": "corrected description",
  "fabric_texture": "more precise texture description",
  "skirt_waistband": "description if found",
  "special_design_features": "any features missed"
}}
```
ONLY include fields that need correction or enhancement. Omit unchanged fields."""


    try:
        zoom_clothing = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[image_part, clothing_zoom_prompt],
            config=types.GenerateContentConfig(temperature=0.1),
        )
        clothing_updates = _parse_json_response(zoom_clothing.text)
        if clothing_updates:
            print(f"[VISION] Pass 3 complete. Clothing zoom found {len(clothing_updates)} corrections/additions.")
            result = _deep_merge(result, clothing_updates)
        else:
            print("[VISION] Pass 3 complete. No clothing corrections needed.")
    except Exception as e:
        print(f"[VISION] ⚠️ Pass 3 (clothing zoom) failed: {e}")

    # ─── Pass 4: ZOOM-FOCUS on JEWELRY DETAILS ───
    print("[VISION] Pass 4/4: ZOOM-FOCUS on jewelry details...")
    jewelry_pieces_str = json.dumps(result.get("jewelry_pieces", []), indent=2, ensure_ascii=False)[:1500]
    jewelry_zoom_prompt = f"""You are zooming into this image to verify JEWELRY details with pixel-level precision.
The current jewelry analysis is:
{jewelry_pieces_str}

NOW ZOOM INTO EACH JEWELRY PIECE INDIVIDUALLY and verify:

For EACH visible jewelry piece, check:

1. **STONE COLORS** — This is the #1 mistake. ZOOM INTO each stone:
   - Are the stones really the color described? Or did the previous pass default to white/clear?
   - Common Indian bridal stone colors: GREEN (emerald), RED (ruby), BLUE (sapphire), PINK, MULTICOLOR
   - If stones described as "white/clear" → RE-EXAMINE closely. Are they actually colored?

2. **DESIGN PATTERN** — ZOOM INTO the piece's overall structure:
   - What is the arrangement of elements? (e.g., "row of 5 oval stones with drops beneath each")
   - Is the current design_pattern description accurate?

3. **MISSING PIECES** — Look at the ENTIRE image for ANY jewelry not yet described:
   - Nose ring/stud (zoom into both nostrils)
   - Rings on fingers
   - Anklets
   - Hair pins/clips
   - Maang tikka side chains

4. **HANGING ELEMENTS** — ZOOM INTO any drops/dangles:
   - Pearl drops: exact count, size, arrangement
   - Chain drops: length, thickness
   - Bead strands: color, material, count

Return ONLY a JSON object with corrections:
```json
{{
  "jewelry_pieces": [
    {{
      "type": "corrected piece type",
      "design_pattern": "verified/corrected design pattern",
      "stones": "VERIFIED stone colors with HEX — corrected if wrong",
      "description": "complete corrected description"
    }}
  ],
  "jewelry_reproduction_checklist": "updated if needed"
}}
```
ONLY include jewelry_pieces that need correction. If a piece is accurate, omit it.
If you find NEW pieces not in the current list, ADD them as new entries."""

    try:
        zoom_jewelry = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[image_part, jewelry_zoom_prompt],
            config=types.GenerateContentConfig(temperature=0.1),
        )
        jewelry_updates = _parse_json_response(zoom_jewelry.text)
        if jewelry_updates:
            print(f"[VISION] Pass 4 complete. Jewelry zoom found {len(jewelry_updates)} corrections/additions.")
            result = _deep_merge(result, jewelry_updates)
        else:
            print("[VISION] Pass 4 complete. No jewelry corrections needed.")
    except Exception as e:
        print(f"[VISION] ⚠️ Pass 4 (jewelry zoom) failed: {e}")

    print(f"[VISION] ✅ Agentic analysis complete (4 passes). Final: {len(result)} fields.")
    return result



# ---------------------------------------------------------------------------
# Detail Mapping Layer — Converts structured JSON into a CONCISE visual prompt
# ---------------------------------------------------------------------------



def build_generation_prompt(details: dict, user_instructions: str = "") -> str:
    """Build a comprehensive generation prompt using BOTH source image AND JSON analysis.
    
    The SOURCE IMAGE is the visual truth, but the JSON analysis provides
    precise text details (colors, embroidery zones, jewelry stone colors)
    that help the model reproduce exact details it might otherwise miss.
    """
    dress = details.get("dress_type") or "clothing"
    primary = details.get("primary_color") or "as shown in IMAGE 1"
    
    # ─── Build DRESS DETAILS block from JSON ───
    dress_lines = []
    
    # Core dress identity
    neckline = details.get("neckline", "")
    if neckline and str(neckline).lower() not in ('null', 'none', ''):
        dress_lines.append(f"• Neckline: {neckline}")
    
    sleeves = details.get("sleeves", "")
    if sleeves and str(sleeves).lower() not in ('null', 'none', ''):
        dress_lines.append(f"• Sleeves: {sleeves}")
    
    embroidery = details.get("embroidery", "")
    if embroidery and str(embroidery).lower() not in ('null', 'none', ''):
        dress_lines.append(f"• Embroidery: {embroidery}")
    
    border_design = details.get("border_design", "")
    if border_design and str(border_design).lower() not in ('null', 'none', ''):
        dress_lines.append(f"• Borders: {border_design}")
    
    embellishments = details.get("embellishments", "")
    if embellishments and str(embellishments).lower() not in ('null', 'none', ''):
        dress_lines.append(f"• Embellishments: {embellishments}")
    
    latkan = details.get("latkan_tassels", "")
    if latkan and str(latkan).lower() not in ('null', 'none', 'none'):
        dress_lines.append(f"• Latkans/Tassels: {latkan}")
    
    special = details.get("special_design_features", "")
    if special and str(special).lower() not in ('null', 'none', ''):
        dress_lines.append(f"• Special Features: {special}")
    
    # Secondary colors
    secondary = details.get("secondary_colors", [])
    if isinstance(secondary, list) and secondary:
        sec_str = ", ".join([f"{c.get('name','')} ({c.get('hex','')}) on {c.get('location','')}" for c in secondary if isinstance(c, dict)])
        if sec_str:
            dress_lines.append(f"• Colors: Primary={primary}, Secondary={sec_str}")
    
    dress_details_block = ""
    if dress_lines:
        dress_details_block = "\n".join(dress_lines)
    
    # Reproduction checklists
    dress_checklist = details.get("dress_reproduction_checklist", "")
    if isinstance(dress_checklist, list):
        dress_checklist = "\n".join(dress_checklist)
    
    jewelry_checklist = details.get("jewelry_reproduction_checklist", "")
    if isinstance(jewelry_checklist, list):
        jewelry_checklist = "\n".join(jewelry_checklist)
    
    # ─── Extract EXPLICIT jewelry details from JSON ───
    jewelry_color_lines = []
    jewelry_pieces = details.get("jewelry_pieces", [])
    if isinstance(jewelry_pieces, list):
        for piece in jewelry_pieces:
            if not isinstance(piece, dict):
                continue
            ptype = piece.get("type", "jewelry piece")
            design_pattern = piece.get("design_pattern", "")
            metal_hex = piece.get("material_color_hex", "")
            stones = piece.get("stones", "")
            pearls = piece.get("pearls", "")
            enamel = piece.get("enamel_meenakari", "")
            dangles = piece.get("dangling_elements", "")
            dimensions = piece.get("dimensions", "")
            visual_weight = piece.get("visual_weight", "")
            desc = piece.get("description", "")
            
            color_parts = [f"  • {ptype}:"]
            if design_pattern and str(design_pattern).lower() not in ('null', 'none', ''):
                color_parts.append(f"    Design: {design_pattern}")
            if metal_hex:
                color_parts.append(f"    Metal: {metal_hex}")
            if stones and str(stones).lower() not in ('null', 'none', ''):
                color_parts.append(f"    Stones: {stones}")
            if pearls and str(pearls).lower() not in ('null', 'none', ''):
                color_parts.append(f"    Pearls: {pearls}")
            if enamel and str(enamel).lower() not in ('null', 'none', ''):
                color_parts.append(f"    Enamel: {enamel}")
            if dangles and str(dangles).lower() not in ('null', 'none', ''):
                color_parts.append(f"    Drops/Dangles: {dangles}")
            if dimensions and str(dimensions).lower() not in ('null', 'none', ''):
                color_parts.append(f"    SIZE/Dimensions: {dimensions} ← MATCH THIS EXACT SIZE!")
            if visual_weight and str(visual_weight).lower() not in ('null', 'none', ''):
                color_parts.append(f"    Visual Weight: {visual_weight}")
            if desc and str(desc).lower() not in ('null', 'none', '') and len(color_parts) <= 3:
                color_parts.append(f"    Full: {desc}")
            
            if len(color_parts) > 1:
                jewelry_color_lines.append("\n".join(color_parts))
    
    jewelry_details_block = ""
    if jewelry_color_lines:
        jewelry_details_block = (
            "\n\n═══ EXACT JEWELRY — PIECE BY PIECE (MUST MATCH IMAGE 1) ═══\n"
            + "\n".join(jewelry_color_lines)
            + "\n🚨 These are analyzed from the ACTUAL source image. Reproduce EACH piece "
            "with these EXACT designs, colors, stone types. Do NOT default to white/clear."
            "\n⚠️ JEWELRY SIZE RULE: Every jewelry piece MUST be the EXACT SAME SIZE as in IMAGE 1. "
            "Do NOT make jewelry smaller or larger. If the necklace is big and heavy in IMAGE 1, "
            "it must be big and heavy in the output. If earrings are long chandeliers, output "
            "long chandeliers — NOT small studs. MATCH THE SCALE EXACTLY."
        )
    
    # Dupatta details
    dupatta_draping = details.get("dupatta_draping") or ""
    dupatta_details = details.get("dupatta_details") or ""
    dupatta_block = ""
    if dupatta_draping or dupatta_details:
        dupatta_block = "\n\n═══ DUPATTA/SCARF ═══"
        if dupatta_draping:
            dupatta_block += f"\nDraping Path: {dupatta_draping}"
        if dupatta_details:
            dupatta_block += f"\nDetails: {dupatta_details}"
    
    # User instructions block
    user_block = ""
    if user_instructions and user_instructions.strip():
        user_block = f"""

═══ USER'S CUSTOM INSTRUCTIONS (HIGH PRIORITY) ═══
{user_instructions.strip()}"""
    
    prompt = f"""YOU MUST COPY THE EXACT OUTFIT FROM IMAGE 1 ONTO THE PERSON IN IMAGE 2.
Use BOTH the source image AND the text details below to achieve 100% accuracy.

═══ #1 RULE: IMAGE 1 + TEXT DETAILS = YOUR REFERENCE ═══
ZOOM INTO IMAGE 1 and CROSS-CHECK with the text details below:
• Every color, pattern, embroidery must EXACTLY match IMAGE 1
• Every jewelry piece must match IMAGE 1 — correct stones, correct colors, correct design
• If the text says GREEN stones → verify in IMAGE 1 → output GREEN stones
• If IMAGE 1 shows dense embroidery → output must show SAME density. Do NOT simplify!
{user_block}

═══ DRESS DETAILS (verified from source image) ═══
Outfit: {dress}
Primary Color: {primary}
{dress_details_block if dress_details_block else "See IMAGE 1 for all dress details."}

═══ DRESS REPRODUCTION CHECKLIST (MUST get EVERY item right) ═══
{dress_checklist if dress_checklist else "Copy ALL dress details exactly from IMAGE 1."}
{jewelry_details_block}

═══ JEWELRY REPRODUCTION CHECKLIST ═══
{jewelry_checklist if jewelry_checklist else "Copy ALL jewelry exactly from IMAGE 1."}
{dupatta_block}

═══ ABSOLUTE RULES — NEVER VIOLATE ═══
1. FACE/BODY/HAIR/SKIN from IMAGE 2 → 100% UNCHANGED — do NOT alter the person
2. CLOTHES + JEWELRY from IMAGE 1 → 100% COPIED — every detail, every color, every stone
3. Background from IMAGE 2 (unless user says otherwise)
4. Dress must look naturally worn — proper fit, realistic draping, natural shadows
5. Output SINGLE photorealistic image — NEVER a collage, NEVER two people, NEVER side-by-side
6. EMBROIDERY: Match the EXACT density and pattern from IMAGE 1. Do NOT simplify to plain fabric
7. JEWELRY STONES: Match EXACT colors — Green=green, Red=red, Blue=blue. NEVER default to white
8. JEWELRY SIZE: Each jewelry piece MUST be the EXACT SAME SIZE/SCALE as in IMAGE 1.
   Big necklace → big necklace. Long earrings → long earrings. Heavy bangles → heavy bangles.
   Do NOT shrink, enlarge, or simplify ANY jewelry piece. Match proportions EXACTLY.
9. BORDERS/TRIM: Match EXACT width, design, and colors from IMAGE 1
10. Every detail matters — tassels, latkans, scalloped edges, piping, dupatta borders — ALL must match
{"10. FOLLOW USER INSTRUCTIONS: " + user_instructions.strip() if user_instructions and user_instructions.strip() else ""}"""



    return prompt



# ---------------------------------------------------------------------------
# System instruction for the generation model
# ---------------------------------------------------------------------------
# GENERATION_SYSTEM_INSTRUCTION — imported from prompts.py



# ---------------------------------------------------------------------------
# Nano Banana Module — Generates image with clothing transfer
# ---------------------------------------------------------------------------

import time as _time

GENERATION_MODELS = [
    "gemini-2.5-flash-image",
]

def _call_generation_model(source_part, target_part, prompt: str):
    """Call the generation model — source outfit shown FIRST for maximum visual attention."""
    for model_name in GENERATION_MODELS:
        for attempt in range(3):
            try:
                print(f"[GEN] Trying {model_name} (attempt {attempt+1}/3)...")
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[
                        "🔴 IMAGE 1 — SOURCE OUTFIT (COPY THIS EXACTLY onto the person below):",
                        source_part,
                        "🔵 IMAGE 2 — TARGET PERSON (keep this person's face/body/background, REPLACE all clothes):",
                        target_part,
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_modalities=["Text", "Image"],
                        system_instruction=GENERATION_SYSTEM_INSTRUCTION,
                        temperature=0.1,
                    ),
                )
                print(f"[GEN] Success with {model_name}!")
                return resp
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    wait = 10 * (attempt + 1)
                    print(f"[GEN] 503 overloaded — waiting {wait}s before retry...")
                    _time.sleep(wait)
                else:
                    print(f"[GEN] Non-retryable error on {model_name}: {e}")
                    break  # try next model
        print(f"[GEN] All attempts failed for {model_name}, trying next model...")
    
    raise Exception("All generation models failed. Please try again later.")


def _extract_response_parts(response) -> tuple[str | None, bytes | None]:
    """Extract text and image from model response."""
    text_result = None
    image_result = None
    try:
        # Try candidates first (some models use this structure)
        parts = None
        if hasattr(response, 'candidates') and response.candidates:
            parts = response.candidates[0].content.parts
        elif hasattr(response, 'parts') and response.parts:
            parts = response.parts
        
        if parts:
            for part in parts:
                if hasattr(part, 'text') and part.text is not None:
                    text_result = part.text
                elif hasattr(part, 'inline_data') and part.inline_data is not None:
                    image_result = part.inline_data.data
    except Exception as e:
        print(f"[ERROR] Failed to extract response parts: {e}")
        traceback.print_exc()
    return text_result, image_result


# ---------------------------------------------------------------------------
# Agentic Verification Module — Compares source vs generated for accuracy
# ---------------------------------------------------------------------------

# VERIFICATION_PROMPT — imported from prompts.py



def verify_output(source_bytes: bytes, source_mime: str,
                  generated_bytes: bytes) -> dict:
    """Compare source dress image vs generated output to find differences."""
    print("[VERIFY] Comparing source vs generated image...")
    
    source_part = types.Part.from_bytes(data=source_bytes, mime_type=source_mime)
    gen_part = types.Part.from_bytes(data=generated_bytes, mime_type="image/png")
    
    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                source_part,
                "👆 IMAGE 1 — SOURCE (the ORIGINAL outfit). This is the TRUTH.",
                gen_part,
                "👆 IMAGE 2 — GENERATED (AI output). Compare clothing/jewelry with IMAGE 1.",
                VERIFICATION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,  # Low temperature for precise comparison
            ),
        )
        
        result = _parse_json_response(response.text)
        score = result.get("match_score", 0)
        diffs = result.get("differences", [])
        print(f"[VERIFY] Match score: {score}/100, Differences found: {len(diffs)}")
        for d in diffs:
            print(f"  [{d.get('severity', '?')}] {d.get('feature', '?')}: {d.get('fix_instruction', '')[:80]}")
        return result
        
    except Exception as e:
        print(f"[VERIFY] Verification failed: {e}")
        traceback.print_exc()
        return {"match_score": -1, "differences": [], "overall_assessment": f"Verification failed: {e}"}


def _build_refinement_prompt(details: dict, differences: list, user_instructions: str = "") -> str:
    """Build a focused correction prompt from verification differences."""
    
    # Format differences into actionable fixes
    fix_lines = []
    for i, diff in enumerate(differences, 1):
        severity = diff.get("severity", "CRITICAL")
        feature = diff.get("feature", "unknown")
        fix = diff.get("fix_instruction", "Match the source image")
        fix_lines.append(f"  {i}. [{severity}] {feature}: {fix}")
    
    fixes_block = "\n".join(fix_lines) if fix_lines else "No specific fixes — match source image more closely."
    
    dress_type = details.get("dress_type", "clothing")
    primary_color = details.get("primary_color", "as described")
    checklist = details.get("dress_reproduction_checklist", "")
    
    user_block = ""
    if user_instructions and user_instructions.strip():
        user_block = f"\n\n═══ USER INSTRUCTIONS (HIGH PRIORITY — MUST FOLLOW) ═══\n{user_instructions.strip()}"
    
    prompt = f"""REFINEMENT — Your previous attempt (IMAGE 3) had issues. Fix them.

Look at the SOURCE OUTFIT (IMAGE 1) very carefully. Now compare it to your
PREVIOUS ATTEMPT (IMAGE 3). Fix THESE specific differences:

═══ ISSUES FOUND — FIX EACH ONE ═══
{fixes_block}
{user_block}

═══ OUTFIT REFERENCE ═══
Type: {dress_type}
Primary Color: {primary_color}
{('Key Features: ' + str(checklist)) if checklist else ''}

═══ HOW TO FIX ═══
1. ZOOM INTO each problem area in the SOURCE image (IMAGE 1)
2. Compare that exact area in your PREVIOUS ATTEMPT (IMAGE 3)
3. Edit your previous attempt to match the source — region by region
4. EMBROIDERY: If the source shows dense, heavy embroidery — match that EXACT density.
   Do NOT simplify to light/sparse embroidery.
5. JEWELRY: If the source shows specific jewelry — replicate EACH piece exactly.
   Match the metal color, stone count, chain style, and size.
   JEWELRY MUST BE THE EXACT SAME SIZE. Do NOT shrink or enlarge any piece.
   Big necklace = big necklace. Long earrings = long earrings. Match proportions EXACTLY.
6. COLORS: Match the EXACT shade from the source. Not similar — IDENTICAL.
7. Keep the PERSON (IMAGE 2) unchanged — face, skin, hair, body, pose, background.
8. Output must be photorealistic with natural fit and proper shadows."""

    
    return prompt


def _call_refinement_model(source_part, target_part, prev_gen_part, prompt: str):
    """Call generation model for refinement — source outfit shown FIRST."""
    for attempt in range(3):
        try:
            print(f"[REFINE] Attempt {attempt+1}/3...")
            resp = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[
                    "🔴 OUTFIT REFERENCE — the outfit MUST look EXACTLY like this:",
                    source_part,
                    "🔵 PERSON — keep this face/body/background:",
                    target_part,
                    "🟡 PREVIOUS ATTEMPT — edit THIS to fix the issues listed below:",
                    prev_gen_part,
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_modalities=["Text", "Image"],
                    system_instruction=GENERATION_SYSTEM_INSTRUCTION,
                    temperature=0.25,
                ),
            )
            return resp
        except Exception as e:
            err_str = str(e)
            if "503" in err_str or "UNAVAILABLE" in err_str:
                wait = 10 * (attempt + 1)
                print(f"[REFINE] 503 — waiting {wait}s...")
                _time.sleep(wait)
            else:
                print(f"[REFINE] Error: {e}")
                raise
    raise Exception("Refinement model failed after 3 attempts.")


def generate_image(source_image_bytes: bytes, source_mime: str,
                   target_image_bytes: bytes, target_mime: str,
                   details: dict, user_instructions: str = "") -> dict:
    """
    Agentic Virtual Try-On with self-verification loop.
    
    Pipeline:
      1. Generate initial clothing transfer
      2. Verify: Compare source vs generated using vision model
      3. If match_score < 90: Refine with focused correction prompt (max 2 rounds)
    
    Returns dict with: image_bytes, text, verification_score, corrections_applied
    """
    prompt = build_generation_prompt(details, user_instructions)

    # Log prompt (truncated)
    print("=" * 60)
    print("GENERATION PROMPT (truncated):")
    print("=" * 60)
    print(prompt[:400] + "..." if len(prompt) > 400 else prompt)
    print("=" * 60)

    source_part = types.Part.from_bytes(data=source_image_bytes, mime_type=source_mime)
    target_part = types.Part.from_bytes(data=target_image_bytes, mime_type=target_mime)

    # ─── Stage 1: Initial Generation ───
    print("[PIPELINE] Stage 1: Initial Generation...")
    image_result = None
    text_result = None
    
    try:
        response = _call_generation_model(source_part, target_part, prompt)
        text_result, image_result = _extract_response_parts(response)
    except Exception as e:
        print(f"[ERROR] Generation attempt 1 failed: {e}")
        traceback.print_exc()

    # Retry with simplified prompt if no image
    if image_result is None:
        print("[RETRY] No image in first attempt. Retrying with simplified prompt...")
        simple_prompt = (
            f"Copy the EXACT outfit and jewelry from IMAGE 1 onto the person in IMAGE 2. "
            f"The outfit is: {details.get('dress_type', 'clothing')}. "
            f"Primary color: {details.get('primary_color', 'not specified')}. "
            f"Keep the person's face, body, hair, skin, and background EXACTLY the same. "
            f"Only change their clothes and jewelry to match IMAGE 1."
        )
        try:
            response = _call_generation_model(source_part, target_part, simple_prompt)
            text_result, image_result = _extract_response_parts(response)
        except Exception as e:
            print(f"[ERROR] Generation attempt 2 failed: {e}")
            traceback.print_exc()

    if image_result is None:
        return {
            "image_bytes": None,
            "text": text_result,
            "prompt": prompt,
            "verification_score": -1,
            "corrections_applied": [],
        }

    # ─── Stage 2: Score-only verification (NO refinement — first pass must be accurate) ───
    print("[PIPELINE] Stage 2: Verifying output (score only)...")
    score = -1
    try:
        verification = verify_output(source_image_bytes, source_mime, image_result)
        score = verification.get("match_score", -1)
        diffs = verification.get("differences", [])
        print(f"[PIPELINE] ✅ Score: {score}/100")
        if diffs:
            print(f"[PIPELINE] Differences noted ({len(diffs)}):")
            for d in diffs[:5]:
                sev = d.get("severity", "?")
                feat = d.get("feature", "unknown")
                print(f"  [{sev}] {feat}: {d.get('fix_instruction', '')[:80]}")
    except Exception as e:
        print(f"[PIPELINE] Verification failed: {e}")

    print(f"\n[PIPELINE] ✅ Complete. Score: {score}/100 (single pass)")
    
    return {
        "image_bytes": image_result,
        "text": text_result,
        "prompt": prompt,
        "verification_score": score,
        "corrections_applied": [],
    }



# ---------------------------------------------------------------------------
# Vision-First Pipeline — Extract 100% outfit details, then generate
# ---------------------------------------------------------------------------

# VISION_EXTRACT_PROMPT — imported from prompts.py



def _extract_outfit_details(source_image_bytes: bytes, source_mime: str) -> str:
    """
    Vision-first: Extract 100% outfit details from source image using text model.
    Returns detailed text description covering every visual element.
    """
    source_part = types.Part.from_bytes(data=source_image_bytes, mime_type=source_mime)
    try:
        resp = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[source_part, VISION_EXTRACT_PROMPT],
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a master fashion analyst. Your job is to capture EVERY visual detail "
                    "of clothing and jewelry from photos. Your descriptions must be so complete that "
                    "an AI image model can recreate the outfit with 100% accuracy. "
                    "Miss NOTHING — every embroidery motif, every color shade, every jewelry element."
                ),
                temperature=0.2,
            ),
        )
        details = resp.text.strip()
        print(f"[VISION] ✅ Extracted outfit details ({len(details)} chars)")
        return details
    except Exception as e:
        print(f"[VISION] ❌ Extraction failed: {e}")
        traceback.print_exc()
        return ""


def generate_image_direct(source_image_bytes: bytes, source_mime: str,
                          target_image_bytes: bytes, target_mime: str,
                          user_instructions: str = "",
                          analysis_json: dict = None) -> dict:
    """
    Vision-first clothing transfer pipeline (SINGLE PASS):
      Uses pre-analyzed JSON (from UI) or falls back to vision extraction.
      Pipeline: JSON → Generate → Score (single pass, no refinement)
    """
    target_part = types.Part.from_bytes(data=target_image_bytes, mime_type=target_mime)
    source_part = types.Part.from_bytes(data=source_image_bytes, mime_type=source_mime)

    # ─── Step 1: Build prompt from analysis JSON ───
    if analysis_json:
        print("[DIRECT] Using pre-analyzed JSON to build generation prompt...")
        prompt = build_generation_prompt(analysis_json, user_instructions)
        details = analysis_json
    else:
        # Fallback: extract details on the fly
        print("[DIRECT] No pre-analyzed JSON — extracting outfit details...")
        outfit_details = _extract_outfit_details(source_image_bytes, source_mime)
        if not outfit_details:
            return {"image_bytes": None, "text": "Failed to extract outfit details", "verification_score": -1, "corrections_applied": []}
        prompt = (
            f"REPLACE ALL CLOTHING on the person with the outfit described below.\n\n"
            f"═══ OUTFIT TO REPRODUCE ═══\n"
            f"{outfit_details}\n"
            f"═══ END OUTFIT DETAILS ═══\n\n"
            f"INSTRUCTIONS:\n"
            f"- Remove the person's ENTIRE current outfit\n"
            f"- Dress them in the COMPLETE outfit described above\n"
            f"- Do NOT keep any of their original clothing\n"
            f"- Face, hair, skin tone, body, pose, background = UNCHANGED\n"
            f"- Output SINGLE photo — no collage, no merging\n"
            f"- Photorealistic result"
        )
        if user_instructions and user_instructions.strip():
            prompt += f"\n\nUSER INSTRUCTIONS (HIGH PRIORITY): {user_instructions.strip()}"
        details = {}

    # ─── Step 2: Initial Generation ───
    print("[DIRECT] Generating clothing transfer...")
    try:
        response = _call_generation_model(source_part, target_part, prompt)
        text_result, image_result = _extract_response_parts(response)
    except Exception as e:
        print(f"[DIRECT] Generation failed: {e}")
        traceback.print_exc()
        return {"image_bytes": None, "text": str(e), "verification_score": -1, "corrections_applied": []}

    if image_result is None:
        print("[DIRECT] No image returned.")
        return {"image_bytes": None, "text": text_result, "verification_score": -1, "corrections_applied": []}

    # ─── Step 3: Score-only verification (NO refinement — first pass must be accurate) ───
    print("[DIRECT] Verifying output (score only)...")
    score = -1
    try:
        verification = verify_output(source_image_bytes, source_mime, image_result)
        score = verification.get("match_score", -1)
        diffs = verification.get("differences", [])
        print(f"[DIRECT] ✅ Score: {score}/100")
        if diffs:
            print(f"[DIRECT] Differences noted ({len(diffs)}):")
            for d in diffs[:5]:
                sev = d.get("severity", "?")
                feat = d.get("feature", "unknown")
                print(f"  [{sev}] {feat}: {d.get('fix_instruction', '')[:80]}")
    except Exception as e:
        print(f"[DIRECT] Verification failed: {e}")

    print(f"\n[DIRECT] ✅ Complete. Score: {score}/100 (single pass)")
    return {
        "image_bytes": image_result,
        "text": text_result,
        "verification_score": score,
        "corrections_applied": [],
    }



# ---------------------------------------------------------------------------
# Standalone Dress Reproduction (No Target Person)
# ---------------------------------------------------------------------------

def generate_dress_standalone(source_image_bytes: bytes, source_mime: str,
                              user_instructions: str = "",
                              analysis_json: dict = None) -> dict:
    """
    Vision-first standalone dress generation (SINGLE PASS):
      Uses pre-analyzed JSON (from UI) or falls back to vision extraction.
      Pipeline: JSON → Generate → Score (single pass, no refinement)
    """
    source_part = types.Part.from_bytes(data=source_image_bytes, mime_type=source_mime)
    has_custom_prompt = bool(user_instructions and user_instructions.strip())

    # ─── Step 1: Build prompt from analysis JSON ───
    if analysis_json:
        print("[STANDALONE] Using pre-analyzed JSON to build generation prompt...")
        # Extract outfit details text from JSON for standalone prompt
        outfit_details_lines = []
        for key, val in analysis_json.items():
            if val and str(val).lower() not in ('null', 'none', 'n/a', ''):
                label = key.replace('_', ' ').title()
                if isinstance(val, (list, dict)):
                    val = json.dumps(val, ensure_ascii=False)
                outfit_details_lines.append(f"• {label}: {val}")
        outfit_details = "\n".join(outfit_details_lines)
    else:
        # Fallback: extract details on the fly
        print("[STANDALONE] No pre-analyzed JSON — extracting outfit details...")
        outfit_details = _extract_outfit_details(source_image_bytes, source_mime)
        if not outfit_details:
            return {"image_bytes": None, "text": "Failed to extract outfit details", "verification_score": -1, "corrections_applied": []}

    # ─── Step 2: Generate once from JSON ───
    if has_custom_prompt:
        gen_prompt = (
            f"{user_instructions.strip()}\n\n"
            f"═══ OUTFIT TO REPRODUCE ═══\n"
            f"{outfit_details}\n"
            f"═══ END OUTFIT DETAILS ═══\n\n"
            f"Use the attached photo as visual reference. Reproduce every detail with 100% accuracy."
        )
    else:
        gen_prompt = (
            f"Create a flat-lay product photo of this outfit.\n\n"
            f"═══ OUTFIT TO REPRODUCE ═══\n"
            f"{outfit_details}\n"
            f"═══ END OUTFIT DETAILS ═══\n\n"
            f"RULES:\n"
            f"- NO person, NO body, NO mannequin — ONLY the garments and jewelry\n"
            f"- Lay all items flat on a white surface: dress/lehenga, blouse, dupatta, jewelry\n"
            f"- Top-down / bird's eye view\n"
            f"- Every detail above must match 100%: embroidery, colors, patterns, jewelry\n"
            f"- Professional e-commerce product photography\n"
            f"- Use the attached photo as visual reference for exact details"
        )

    print("[STANDALONE] Generating product photo (single pass, maximum detail)...")
    try:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    # model="gemini-2.5-flash-image",
                    model="gemini-3-pro-image-preview",
                    contents=[gen_prompt, source_part],
                    config=types.GenerateContentConfig(
                        response_modalities=["Text", "Image"],
                        system_instruction=(
                            "You are a PIXEL-PERFECT product photographer. "
                            "You ZOOM INTO the reference image and reproduce EVERY detail with 100% accuracy. "
                            "NEVER simplify, NEVER approximate, NEVER skip ANY detail. "
                            "Match exact colors, exact patterns, exact embroidery density, exact jewelry stones. "
                            "NEVER include any person, body, face, or mannequin. "
                            "Show ONLY garments and jewelry on a clean surface. "
                            "YOU MUST GET IT 100% RIGHT ON THE FIRST ATTEMPT."
                        ),
                        temperature=0.0,
                    ),
                )
                break
            except Exception as e:
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    _time.sleep(10 * (attempt + 1))
                else:
                    raise
        text_result, image_result = _extract_response_parts(response)
    except Exception as e:
        print(f"[STANDALONE] Generation failed: {e}")
        traceback.print_exc()
        return {"image_bytes": None, "text": str(e), "verification_score": -1, "corrections_applied": []}

    if image_result is None:
        return {"image_bytes": None, "text": text_result or "No image generated", "verification_score": -1, "corrections_applied": []}

    # ─── Step 3: Score-only verification (NO refinement — first pass must be accurate) ───
    print("[STANDALONE] Verifying output (score only)...")
    score = -1
    try:
        verification = verify_output(source_image_bytes, source_mime, image_result)
        score = verification.get("match_score", -1)
        diffs = verification.get("differences", [])
        print(f"[STANDALONE] ✅ Score: {score}/100")
        if diffs:
            print(f"[STANDALONE] Differences noted ({len(diffs)}):")
            for d in diffs[:5]:
                sev = d.get("severity", "?")
                feat = d.get("feature", "unknown")
                print(f"  [{sev}] {feat}: {d.get('fix_instruction', '')[:80]}")
    except Exception as e:
        print(f"[STANDALONE] Verification failed: {e}")

    print(f"\n[STANDALONE] ✅ Complete. Score: {score}/100 (single pass)")
    return {
        "image_bytes": image_result,
        "text": text_result,
        "verification_score": score,
        "corrections_applied": [],
    }






# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Analyze a source image and return structured clothing details."""
    if client is None:
        return jsonify({"error": "GEMINI_API_KEY not configured on server"}), 503
    try:
        if "image" not in request.files:
            return jsonify({"error": "No image file provided"}), 400

        file = request.files["image"]
        image_bytes = file.read()
        mime_type = file.content_type or "image/jpeg"

        details = analyze_image(image_bytes, mime_type)
        return jsonify({"success": True, "details": details})

    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse vision model output as JSON"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompt-preview", methods=["POST"])
def api_prompt_preview():
    """Debug: Return the exact generation prompt that would be sent to the model."""
    try:
        details_str = request.form.get("details") or request.get_json(silent=True, force=True)
        if isinstance(details_str, str):
            details = json.loads(details_str)
        elif isinstance(details_str, dict):
            details = details_str
        else:
            return jsonify({"error": "No details provided"}), 400

        prompt = build_generation_prompt(details)
        return jsonify({"success": True, "prompt": prompt})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate clothing transfer with agentic verification pipeline."""
    if client is None:
        return jsonify({"error": "GEMINI_API_KEY not configured on server"}), 503
    try:
        if "target_image" not in request.files:
            return jsonify({"error": "No target image provided"}), 400
        if "source_image" not in request.files:
            return jsonify({"error": "No source image provided"}), 400

        details_str = request.form.get("details")
        if not details_str:
            return jsonify({"error": "No details JSON provided"}), 400

        details = json.loads(details_str)
        user_instructions = request.form.get("user_instructions", "")

        source_file = request.files["source_image"]
        source_bytes = source_file.read()
        source_mime = source_file.content_type or "image/jpeg"

        target_file = request.files["target_image"]
        target_bytes = target_file.read()
        target_mime = target_file.content_type or "image/jpeg"

        # Run the agentic pipeline (generate → verify → refine)
        result = generate_image(
            source_bytes, source_mime,
            target_bytes, target_mime,
            details, user_instructions,
        )

        image_bytes = result.get("image_bytes")
        if image_bytes is None:
            return jsonify({
                "error": "Model did not return an image. " + (result.get("text") or ""),
                "prompt": result.get("prompt", ""),
            }), 500

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        return jsonify({
            "success": True,
            "image": image_b64,
            "text": result.get("text"),
            "prompt": result.get("prompt", ""),
            "verification_score": result.get("verification_score", -1),
            "corrections_applied": result.get("corrections_applied", []),
        })

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid details JSON"}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate-direct", methods=["POST"])
def api_generate_direct():
    """Direct clothing transfer or standalone dress reproduction.
    If target_image is provided: virtual try-on (dress on person).
    If target_image is NOT provided: standalone dress reproduction.
    """
    if client is None:
        return jsonify({"error": "GEMINI_API_KEY not configured on server"}), 503
    try:
        if "source_image" not in request.files:
            return jsonify({"error": "No source image provided"}), 400

        source_file = request.files["source_image"]
        source_bytes = source_file.read()
        source_mime = source_file.content_type or "image/jpeg"
        user_instructions = request.form.get("user_instructions", "")

        # Parse pre-analyzed JSON from frontend (if available)
        analysis_json = None
        analysis_json_str = request.form.get("analysis_json", "")
        if analysis_json_str:
            try:
                analysis_json = json.loads(analysis_json_str)
                print(f"[API] Using pre-analyzed JSON ({len(analysis_json)} fields)")
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[API] Failed to parse analysis_json: {e}")

        # Check if target image is provided
        if "target_image" in request.files:
            # Virtual try-on mode
            target_file = request.files["target_image"]
            target_bytes = target_file.read()
            target_mime = target_file.content_type or "image/jpeg"

            result = generate_image_direct(
                source_bytes, source_mime,
                target_bytes, target_mime,
                user_instructions,
                analysis_json=analysis_json,
            )
        else:
            # Standalone dress reproduction mode
            result = generate_dress_standalone(
                source_bytes, source_mime,
                user_instructions,
                analysis_json=analysis_json,
            )

        image_bytes = result.get("image_bytes")
        if image_bytes is None:
            return jsonify({
                "error": "Model did not return an image. " + (result.get("text") or ""),
            }), 500

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        return jsonify({
            "success": True,
            "image": image_b64,
            "text": result.get("text"),
            "verification_score": result.get("verification_score", -1),
            "corrections_applied": result.get("corrections_applied", []),
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
