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

load_dotenv()

app = Flask(__name__)
CORS(app)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ---------------------------------------------------------------------------
# Agentic Vision Module — Extracts structured details from an image
# ---------------------------------------------------------------------------

VISION_PROMPT = """You are an ELITE visual analyst with pixel-level precision in fashion, textiles,
jewelry, color science, and garment construction. Your output will be fed DIRECTLY into an
AI image-generation model to PERFECTLY RECREATE this exact clothing, jewelry, and styling
on a different person. Every missing or inaccurate detail = a visible flaw in the output image.

## ━━━ ABSOLUTE RULES (NEVER VIOLATE) ━━━
1. **EXACT COLORS**: Every color MUST have BOTH a precise name AND HEX code.
   Example: "Deep burgundy wine (#722F37)". ALL colors — primary, secondary, accent,
   trim, thread, lining, stone, metal — without exception.
2. **PRECISE COUNTING**: Count ONE BY ONE. NEVER use "some", "several", "many", "a few",
   "multiple", or "various". Give EXACT numbers or "approximately N (estimated)".
3. **ZERO SKIP POLICY**: If a detail exists — no matter how small — it MUST appear.
   A tiny thread, a micro-print, a subtle stitch = MUST BE DESCRIBED.
4. **NO HALLUCINATION**: Only what is visually confirmed. Uncertain → prefix "appears to be".
5. **SPATIAL PRECISION**: WHERE each element is — "center-front", "left shoulder",
   "3cm below collar", "along hemline", "at waistline".

## ━━━ ANALYSIS PROTOCOL ━━━

### STEP 1: OVERVIEW
- Garment type, overall silhouette, style era/category.
- Person's pose and body angle (affects garment visibility).

### STEP 2: COLOR DEEP-DIVE
- Examine EACH garment region: body-front, body-back, sleeves (L/R), collar, cuffs, trim, lining.
- For EACH region: base color (name + hex), color in light (hex), color in shadow (hex).
- Gradients, ombré effects, fading, color transitions → start/end hex codes.
- Color shifts from fabric texture (satin sheen vs matte base).

### STEP 3: FABRIC & TEXTURE
- Fabric type with confidence % (cotton, silk, chiffon, denim, velvet, etc.).
- Surface: matte/glossy/semi-sheer/rough/smooth/ribbed/brushed/napped.
- Weave pattern if visible: plain, twill, satin, basket, herringbone, jacquard.
- Thread visibility, thickness, surface irregularities (pilling, fuzz, slubs).
- Fabric weight: lightweight/medium/heavy — how it drapes.
- Transparency: opaque/semi-sheer/sheer.

### STEP 4: CONSTRUCTION & STRUCTURE (COUNT EVERYTHING)
- ALL panels (count), seams (type + position), darts (count + position).
- Pleats (type + count), tucks, gathers, ruching — each with position.
- Pockets: count, type, position, size.
- Vents/slits: count, position, length.
- Collar/neckline: exact type, depth, width, stand height.
- Sleeves: type, length, cuff style, cuff closure.
- Hemline: style, depth of hem fold.
- Closures: count, type, material, color+hex, position.
- Buttons: EXACT count, diameter, shape, material, color+hex, holes, spacing.

### STEP 5: PATTERN & PRINT
- Pattern type: solid/striped/plaid/floral/geometric/abstract/paisley/etc.
- Motif shape, size, color palette (all hex), spacing, orientation, repeat count.
- Pattern alignment at seams: matched/offset/random.
- Print technique: screen-printed/digital/woven-in/embroidered/block-printed.

### ★ STEP 6: SPECIAL DESIGN FEATURES & MICRO-DETAILS (CRITICAL — DO NOT SKIP) ★
**This is the MOST IMPORTANT step. Many models skip this. YOU MUST NOT.**

Mentally ZOOM IN to every 5cm × 5cm section of the garment and scan for:
- **Piping/edging**: Any colored piping, contrast edging, bias tape along seams or edges
- **Trim/borders**: Lace trim, ribbon borders, embroidered borders, printed borders at hem/cuffs/neckline
- **Topstitching**: Decorative stitching lines, contrast thread stitching, double-needle stitching
- **Gathering/shirring**: Where fabric is gathered, elastic shirring, smocking
- **Cutwork/laser-cut**: Any cut-out patterns, perforations, laser-cut designs
- **Appliqué/patchwork**: Fabric pieces stitched on, patches, quilted sections
- **Prints within prints**: Small secondary prints/motifs inside larger patterns
- **Beading/sequin work**: Even if just a few beads — count them, describe arrangement
- **Embroidery details**: Thread colors (hex), stitch types (satin/chain/cross), motif shapes, coverage
- **Logo/label/text**: Any visible branding, labels, text, monograms
- **Belt loops/tabs**: Functional or decorative loops, tabs, straps
- **Drawstrings/ties**: Cords, ribbons, bow ties, cinch details
- **Ruffle/frill details**: Layers of ruffles, ruffle width, spacing, direction
- **Wrap/drape details**: How fabric wraps, overlaps, crosses-over
- **Asymmetric elements**: One side different from other — note exactly how
- **Hidden details**: Parts partially visible — inner collar, peek of lining, inside of cuff

### STEP 7: EMBELLISHMENTS
- Count EVERY sequin, bead, rhinestone, pearl, embroidery motif, appliqué, lace panel,
  ruffle, ribbon, bow, fringe, tassel.
- For each: material, color+hex, size, position on garment.
- Embroidery: thread colors (all hex), stitch types, motif description, coverage area.

### STEP 8: JEWELRY INVENTORY
- Each piece: type, metal type + finish, metal color hex.
- Stones: EXACT count, cut, color+hex, size, setting type, arrangement.
- Chain: link shape, count, thickness.
- Design elements: dots, engravings, filigree, beads, pendants.

### STEP 9: ACCESSORIES
- Belt, scarf/dupatta, watch, bag, sunglasses, hair accessories, footwear.
- All with full color+hex descriptions.

### STEP 10: FIT & DRAPE
- Fit: tight/fitted/relaxed/oversized/draped.
- Where it clings vs where it falls loose.
- Count major fold lines and their direction.
- Garment length relative to body landmarks.

### STEP 11: ENVIRONMENT & LIGHTING
- Light source direction, intensity, temperature (warm/cool/neutral).
- Shadow patterns on garment. Background colors + hex.

### STEP 12: FINAL CROSS-VERIFICATION
- Re-scan the ENTIRE image one final time.
- Did you miss ANY small detail? Tiny print? Subtle stitch? Hidden element?
- Verify all counts. Confirm all hex codes.

## ━━━ OUTPUT FORMAT ━━━

Return a valid JSON object with these fields (null if not applicable):

{
  "dress_type": "Garment type with sub-category",
  "style_era": "Style period/aesthetic",
  "primary_color": "Exact shade name + hex code",
  "primary_color_hex": "#hex only",
  "secondary_colors": [{"name": "Color", "hex": "#hex", "location": "Where"}],
  "accent_colors": [{"name": "Color", "hex": "#hex", "location": "Where"}],
  "color_in_shadows": "Primary color in shadow — name + hex",
  "color_in_highlights": "Primary color in highlights — name + hex",
  "color_variations_by_region": "How color differs across regions — each with hex",
  "fabric": "Fabric type + confidence %",
  "fabric_weight": "Weight + drape behavior",
  "texture": "Surface texture description",
  "texture_detail": "Micro-level texture: thread, weave, sheen, irregularities",
  "transparency": "Opaque / Semi-sheer / Sheer",
  "pattern": "Pattern type",
  "pattern_details": "Full description: motif, size, spacing, orientation, repeat count",
  "pattern_colors": [{"name": "Color", "hex": "#hex", "role": "background/motif/outline"}],
  "pattern_alignment": "How pattern aligns at seams",
  "fit": "Fit style + drape description",
  "fit_on_body": "Where clings, where loose, how falls",
  "silhouette": "Overall garment shape from shoulder to hem",
  "sleeves": "Type, length, width, cuff style, cuff closure details",
  "neckline": "Type, depth, width, collar stand height",
  "length": "Garment length relative to body",
  "hemline": "Hem style + finish",
  "buttons": "EXACT count, diameter, shape, material, color+hex, holes, spacing, positions",
  "buttonholes": "Count, style, thread color+hex",
  "embellishments": "EXACT count + full description of every decorative element with positions",
  "structural_details": "ALL panels, darts, pleats, tucks, gathers — with counts and positions",
  "seams_and_stitching": "Seam types, topstitching, stitch width, thread color+hex",
  "closures": "Each closure: type, count, position, material, color+hex",
  "pockets": "Count, type, position, size",
  "vents_and_slits": "Count, position, length",
  "lining_visible": "Lining color+hex + fabric if visible",
  "special_design_features": "ALL unique design elements that make this garment SPECIAL — piping, trim, borders, contrast edging, decorative stitching, cutwork, wrap details, asymmetric elements, drawstrings, ties, belt loops, tabs. DESCRIBE EACH ONE with position, color+hex, size.",
  "micro_details": "TINY details often missed — small prints within prints, subtle stitch patterns, barely visible embroidery, miniature buttons, hidden snaps, contrast thread at seams, edge finishing method, hem tape color, brand labels/tags visible, monograms, tiny beads or sequins",
  "design_dna": "What makes THIS garment DIFFERENT from a plain/generic version of the same type? List every distinctive feature that sets it apart.",
  "jewelry_pieces": [{"type": "type", "material": "metal + finish", "material_color_hex": "#hex", "stones": "count, cut, color+hex, size, setting, arrangement", "chain_details": "link shape, count, thickness", "design_elements": "dots, engravings, filigree, beads", "dimensions": "size", "position_on_body": "location", "description": "full description"}],
  "accessories": "Every accessory with full details + colors+hex",
  "layering": "Layer count, each layer described with fabric + color",
  "proportions": "Key proportional relationships",
  "draping_and_folds": "COUNT of fold lines, direction, depth, where fabric bunches",
  "garment_condition": "New/worn/wrinkled/crisp/pressed",
  "lighting": "Light direction, intensity, type, color temperature",
  "shadows_on_garment": "Where shadows fall, intensity, color+hex",
  "pose": "Subject pose, body angle, how it affects garment visibility",
  "background": "Background description with colors+hex",
  "overall_style": "Style category / aesthetic",
  "counted_elements_summary": "FINAL count of EVERY countable element with color+hex. Format: 'N x element (color #hex)'",
  "reproduction_notes": "Critical notes for perfect reproduction — asymmetries, unusual construction, hidden details, unique characteristics"
}

## ━━━ CRITICAL OUTPUT RULES ━━━
- Return ONLY the JSON object. No markdown fences. No text before or after.
- EVERY color mention MUST have a hex code — no exceptions.
- Use code_execution tool for precise counting if needed.
- Count one-by-one. Do not round. Exact numbers or "approximately N (estimated)".
- FOR SPECIAL DETAILS: If the garment has ANY unique design features (piping, trim, borders,
  embroidery, prints, cutwork, contrast stitching, asymmetry, etc.), the `special_design_features`
  and `micro_details` fields MUST be filled with comprehensive descriptions. These fields are
  what differentiate a GOOD analysis from a BAD one. DO NOT leave them null or empty.
- Your description must be so detailed that someone who has NEVER seen this image could
  instruct an AI model to generate a pixel-perfect recreation.
"""


def _parse_json_response(raw_text: str) -> dict:
    """Parse JSON from model response, stripping markdown fences if present."""
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
    return json.loads(raw_text)


REFINEMENT_PROMPT = """You are reviewing your own analysis of a clothing image. Your first pass
analysis is shown below, but it has GAPS and MISSING DETAILS.

## YOUR FIRST PASS RESULT:
{first_pass_json}

## YOUR TASK NOW:
Look at the image AGAIN very carefully. Focus on what you MISSED in the first pass.

1. **ZOOM INTO EVERY SECTION** of the garment — neckline area, chest, waist, hem, sleeves, back.
2. **Find details that are null, empty, or weak** in your first pass.
3. **Especially fill these critical fields if they are empty or vague:**
   - `special_design_features` — piping, trim, borders, contrast edging, decorative stitching, cutwork, ties, wraps
   - `micro_details` — tiny prints, subtle stitches, miniature elements, hidden snaps, contrast thread
   - `design_dna` — what makes THIS garment unique vs a plain version
   - `embellishments` — any decorative elements with exact counts
   - `pattern_details` — motif shapes, sizes, spacing, colors
   - `structural_details` — panels, darts, pleats with counts
   - `buttons` — exact count, shape, material
   - `closures` — every closure type

4. **Also verify and correct** any colors — are the HEX codes accurate?
5. **Count again** — are button/stone/bead counts correct?

## OUTPUT:
Return a JSON object with ONLY the fields you are updating or adding.
Do NOT repeat fields that are already correct and complete in the first pass.
Only include fields where you have NEW or BETTER information.
Return ONLY the JSON. No markdown fences. No text before or after.
"""


def analyze_image(image_bytes: bytes, mime_type: str) -> dict:
    """Two-pass analysis: full scan + detail refinement for 100% detail capture."""
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    # ─── PASS 1: Full comprehensive analysis ───
    print("[VISION] Pass 1: Full comprehensive analysis...")
    response1 = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[image_part, VISION_PROMPT],
        config=types.GenerateContentConfig(
            tools=[types.Tool(code_execution=types.ToolCodeExecution)]
        ),
    )
    pass1_result = _parse_json_response(response1.text)
    print(f"[VISION] Pass 1 complete. Got {len(pass1_result)} fields.")

    # ─── Check if refinement is needed ───
    weak_fields = []
    critical_fields = [
        "special_design_features", "micro_details", "design_dna",
        "embellishments", "pattern_details", "structural_details",
        "buttons", "closures", "embellishments", "reproduction_notes",
    ]
    for field in critical_fields:
        val = pass1_result.get(field)
        if not val or str(val).lower() in ("null", "none", "n/a", ""):
            weak_fields.append(field)

    if not weak_fields:
        print("[VISION] All critical fields filled. Skipping Pass 2.")
        return pass1_result

    print(f"[VISION] Pass 2: Refining {len(weak_fields)} weak fields: {weak_fields}")

    # ─── PASS 2: Focused refinement ───
    refinement_prompt = REFINEMENT_PROMPT.format(
        first_pass_json=json.dumps(pass1_result, indent=2, ensure_ascii=False)
    )

    response2 = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[image_part, refinement_prompt],
        config=types.GenerateContentConfig(
            tools=[types.Tool(code_execution=types.ToolCodeExecution)]
        ),
    )

    try:
        pass2_result = _parse_json_response(response2.text)
        print(f"[VISION] Pass 2 complete. Got {len(pass2_result)} updated fields.")

        # Merge: Pass 2 overwrites null/empty fields from Pass 1
        for key, value in pass2_result.items():
            if value and str(value).lower() not in ("null", "none", "n/a", ""):
                existing = pass1_result.get(key)
                if not existing or str(existing).lower() in ("null", "none", "n/a", ""):
                    pass1_result[key] = value
                elif isinstance(value, str) and isinstance(existing, str) and len(value) > len(existing):
                    # Pass 2 has more detail — use it
                    pass1_result[key] = value

    except (json.JSONDecodeError, Exception) as e:
        print(f"[VISION] Pass 2 parse failed ({e}), using Pass 1 only.")

    return pass1_result


# ---------------------------------------------------------------------------
# Detail Mapping Layer — Converts structured JSON into a CONCISE visual prompt
# ---------------------------------------------------------------------------



def build_generation_prompt(details: dict) -> str:
    """Build a generation prompt that includes the FULL extracted JSON.
    
    Instead of manually picking fields (which loses details), we dump the
    entire JSON and add focused instructions. This ensures 100% of the
    extracted details reach the generation model.
    """
    # Quick headline for the model
    dress = details.get("dress_type") or "clothing"
    primary = details.get("primary_color") or "as described"
    
    # Build the full JSON string (pretty-printed for readability)
    full_json = json.dumps(details, indent=2, ensure_ascii=False)
    
    prompt = f"""DRESS THIS PERSON in the exact outfit described below.

═══ OUTFIT SUMMARY ═══
Type: {dress}
Primary Color: {primary}

═══ COMPLETE CLOTHING DETAILS (FOLLOW EVERY DETAIL) ═══
{full_json}

═══ CRITICAL PRIORITIES ═══
1. COLORS: Match EVERY color exactly using the HEX codes above. Primary, secondary, accent — all must be pixel-perfect.
2. PATTERN & DESIGN: Reproduce the exact pattern, motifs, embroidery, embellishments as described.
3. STRUCTURE: Match neckline, sleeves, length, silhouette, buttons, closures precisely.
4. SPECIAL FEATURES: The "special_design_features", "micro_details", and "design_dna" fields describe what makes this outfit UNIQUE — reproduce them exactly.
5. JEWELRY: Add all jewelry pieces exactly as described with correct colors and placement.

═══ ABSOLUTE RULES ═══
• Keep the person's FACE, SKIN, HAIR, BODY, and POSE 100% UNCHANGED.
• Keep the BACKGROUND and LIGHTING exactly the same.
• ONLY change their clothing to match the description above.
• The clothing must look naturally worn — proper fit, draping, and realistic shadows.
• The result MUST be photorealistic — like a real high-quality photograph.
• Do NOT simplify or skip any detail from the JSON above."""

    return prompt


# ---------------------------------------------------------------------------
# System instruction for the generation model
# ---------------------------------------------------------------------------

GENERATION_SYSTEM_INSTRUCTION = (
    "You are an expert virtual try-on / clothing generation AI. "
    "You receive ONE image of a TARGET person and a DETAILED TEXT DESCRIPTION "
    "of the outfit they must wear. "
    "\n\nCRITICAL RULES: "
    "• The TARGET person's FACE, SKIN COLOR, HAIR, BODY SHAPE, and POSE must remain "
    "  100% IDENTICAL — do NOT alter their identity or appearance in ANY way. "
    "• The TARGET image's BACKGROUND and LIGHTING must stay EXACTLY the same. "
    "• ONLY replace the TARGET person's clothing with the outfit described in the text. "
    "• Follow the text description PRECISELY — match every color (use the HEX codes given), "
    "  pattern, fabric texture, structural detail, and embellishment exactly as described. "
    "• Add any jewelry or accessories described in the text. "
    "• The clothing must look naturally worn — proper fit, draping, and shadows "
    "  matching the TARGET person's body shape and pose. "
    "• The final image must be photorealistic — it should look like a real photograph."
)


# ---------------------------------------------------------------------------
# Nano Banana Module — Generates image with clothing transfer
# ---------------------------------------------------------------------------

import time as _time

GENERATION_MODELS = [
    "gemini-2.5-flash-image",
]

def _call_generation_model(target_part, prompt: str):
    """Call the generation model with auto-retry and fallback on 503."""
    for model_name in GENERATION_MODELS:
        for attempt in range(3):
            try:
                print(f"[GEN] Trying {model_name} (attempt {attempt+1}/3)...")
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[
                        target_part,
                        (
                            "This is the TARGET PERSON. Keep their FACE, SKIN, HAIR, BODY, "
                            "and POSE 100% UNCHANGED. Keep the BACKGROUND exactly the same. "
                            "ONLY replace their clothing with the outfit described below.\n\n"
                            + prompt
                        ),
                    ],
                    config=types.GenerateContentConfig(
                        response_modalities=["Text", "Image"],
                        system_instruction=GENERATION_SYSTEM_INSTRUCTION,
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


def generate_image(target_image_bytes: bytes, target_mime: str,
                   details: dict) -> tuple[str | None, bytes | None]:
    """
    Virtual try-on: dress the target person using JSON details (no source image).
    
    Strategy:
      1. Build a detailed prompt from extracted clothing details (JSON)
      2. Send ONLY target image + text prompt to the generation model
      3. If no image returned, retry once with a simplified prompt
    
    Returns (text_response, image_bytes) tuple.
    """
    prompt = build_generation_prompt(details)

    # Log the prompt for debugging
    print("=" * 60)
    print("GENERATION PROMPT SENT TO MODEL:")
    print("=" * 60)
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    print("=" * 60)

    target_part = types.Part.from_bytes(data=target_image_bytes, mime_type=target_mime)

    # Attempt 1: Full prompt
    try:
        response = _call_generation_model(target_part, prompt)
        text_result, image_result = _extract_response_parts(response)
    except Exception as e:
        print(f"[ERROR] Generation attempt 1 failed: {e}")
        traceback.print_exc()
        text_result, image_result = None, None

    # Attempt 2: Retry with simplified prompt if no image was returned
    if image_result is None:
        print("[RETRY] No image in first attempt. Retrying with simplified prompt...")
        simple_prompt = (
            f"Dress this person in the following outfit. "
            f"The outfit is: {details.get('dress_type', 'clothing')}. "
            f"Primary color: {details.get('primary_color', 'not specified')}. "
            f"Fabric: {details.get('fabric', 'not specified')}. "
            f"Pattern: {details.get('pattern', 'solid')}. "
            f"Keep the person's face, body, hair, skin, and background EXACTLY the same. "
            f"Only change their clothes."
        )
        try:
            response = _call_generation_model(target_part, simple_prompt)
            text_result, image_result = _extract_response_parts(response)
        except Exception as e:
            print(f"[ERROR] Generation attempt 2 failed: {e}")
            traceback.print_exc()

    return text_result, image_result


# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Analyze a source image and return structured clothing details."""
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
    """Generate clothing transfer image using Nano Banana (JSON details + target only)."""
    try:
        if "target_image" not in request.files:
            return jsonify({"error": "No target image provided"}), 400

        details_str = request.form.get("details")
        if not details_str:
            return jsonify({"error": "No details JSON provided"}), 400

        details = json.loads(details_str)

        target_file = request.files["target_image"]
        target_bytes = target_file.read()
        target_mime = target_file.content_type or "image/jpeg"

        # Build prompt for response (so UI can show it)
        prompt_text = build_generation_prompt(details)

        text_resp, image_bytes = generate_image(
            target_bytes, target_mime,
            details,
        )

        if image_bytes is None:
            return jsonify({
                "error": "Model did not return an image. " + (text_resp or ""),
                "prompt": prompt_text,
            }), 500

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        return jsonify({
            "success": True,
            "image": image_b64,
            "text": text_resp,
            "prompt": prompt_text,
        })

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid details JSON"}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
