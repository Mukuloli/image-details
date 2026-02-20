// ===================================================================
// Agentic Vision + Nano Banana — Client-Side Logic
// ===================================================================

// State
let sourceImageFile = null;
let targetImageFile = null;
let extractedDetails = null;

// DOM Elements
const sourceUpload = document.getElementById('source-upload');
const sourceInput = document.getElementById('source-input');
const targetUpload = document.getElementById('target-upload');
const targetInput = document.getElementById('target-input');
const analyzeBtn = document.getElementById('analyze-btn');
const generateBtn = document.getElementById('generate-btn');
const detailsPanel = document.getElementById('details-panel');
const originalDisplay = document.getElementById('original-display');
const generatedDisplay = document.getElementById('generated-display');
const downloadBtn = document.getElementById('download-btn');
const statusBar = document.getElementById('status-bar');
const statusText = document.getElementById('status-text');
const genText = document.getElementById('generation-text');

// ---------------------------------------------------------------
// Upload Zone Handlers
// ---------------------------------------------------------------

function setupUploadZone(zone, input, previewEl, onFile) {
    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleFile(file, zone, previewEl, onFile);
        }
    });

    input.addEventListener('change', () => {
        const file = input.files[0];
        if (file) {
            handleFile(file, zone, previewEl, onFile);
        }
    });
}

function handleFile(file, zone, previewEl, onFile) {
    const reader = new FileReader();
    reader.onload = (e) => {
        zone.classList.add('has-image');
        zone.innerHTML = `<img src="${e.target.result}" alt="Preview">`;
        zone.onclick = () => {
            const newInput = document.createElement('input');
            newInput.type = 'file';
            newInput.accept = 'image/*';
            newInput.onchange = () => {
                const f = newInput.files[0];
                if (f) handleFile(f, zone, previewEl, onFile);
            };
            newInput.click();
        };

        if (previewEl) {
            previewEl.innerHTML = `<img src="${e.target.result}" alt="Original">`;
        }

        onFile(file);
    };
    reader.readAsDataURL(file);
}

// Initialize upload zones
setupUploadZone(sourceUpload, sourceInput, originalDisplay, (file) => {
    sourceImageFile = file;
    analyzeBtn.disabled = false;
    showStatus('info', 'Source image loaded — ready to analyze');
});

setupUploadZone(targetUpload, targetInput, null, (file) => {
    targetImageFile = file;
    if (extractedDetails) {
        generateBtn.disabled = false;
        showStatus('info', 'Target image loaded — ready to generate');
    }
});

// ---------------------------------------------------------------
// Status Bar
// ---------------------------------------------------------------

function showStatus(type, message) {
    statusBar.className = `status-bar ${type} visible`;
    statusText.textContent = message;
}

function hideStatus() {
    statusBar.classList.remove('visible');
}

// ---------------------------------------------------------------
// Toggle Details Panel
// ---------------------------------------------------------------

function toggleDetails() {
    const panel = document.getElementById('details-panel');
    const toggle = document.getElementById('details-toggle');
    panel.classList.toggle('collapsed');
    toggle.textContent = panel.classList.contains('collapsed')
        ? '▼ Expand'
        : '▲ Collapse';
}

// ---------------------------------------------------------------
// Analyze Image
// ---------------------------------------------------------------

analyzeBtn.addEventListener('click', async () => {
    if (!sourceImageFile) return;

    analyzeBtn.disabled = true;
    analyzeBtn.classList.add('loading');
    showStatus('info', 'Analyzing with Agentic Vision (2-pass)... this may take a moment');

    const formData = new FormData();
    formData.append('image', sourceImageFile);

    try {
        const resp = await fetch('/api/analyze', {
            method: 'POST',
            body: formData,
        });

        const data = await resp.json();

        if (!resp.ok || !data.success) {
            throw new Error(data.error || 'Analysis failed');
        }

        extractedDetails = data.details;
        renderDetails(extractedDetails);

        // Auto-expand details panel after analysis
        detailsPanel.classList.remove('collapsed');
        const toggle = document.getElementById('details-toggle');
        if (toggle) toggle.textContent = '▲ Collapse';

        showStatus('success', 'Analysis complete — all details extracted');

        if (targetImageFile) {
            generateBtn.disabled = false;
        }

    } catch (err) {
        showStatus('error', `Analysis failed: ${err.message}`);
        console.error(err);
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.classList.remove('loading');
    }
});

// ---------------------------------------------------------------
// Generate Image
// ---------------------------------------------------------------

generateBtn.addEventListener('click', async () => {
    if (!targetImageFile || !extractedDetails) return;

    generateBtn.disabled = true;
    generateBtn.classList.add('loading');
    showStatus('info', 'Generating with Nano Banana... this may take a moment');
    generatedDisplay.innerHTML = `
        <div class="output-placeholder">
            <div class="icon">⏳</div>
            <p>Generating... please wait</p>
        </div>`;

    // Hide prompt debug while generating
    const promptDebug = document.getElementById('prompt-debug');
    const promptContent = document.getElementById('prompt-content');
    promptDebug.classList.remove('visible');
    promptContent.classList.remove('visible');

    const userInstructions = document.getElementById('user-instructions')?.value || '';

    const formData = new FormData();
    formData.append('target_image', targetImageFile);
    formData.append('source_image', sourceImageFile);
    formData.append('details', JSON.stringify(extractedDetails));
    formData.append('user_instructions', userInstructions);

    try {
        const resp = await fetch('/api/generate', {
            method: 'POST',
            body: formData,
        });

        const data = await resp.json();

        if (!resp.ok || !data.success) {
            throw new Error(data.error || 'Generation failed');
        }

        const imgSrc = `data:image/png;base64,${data.image}`;
        generatedDisplay.innerHTML = `<img src="${imgSrc}" alt="Generated Result">`;

        downloadBtn.classList.add('visible');
        downloadBtn.onclick = () => downloadImage(imgSrc, 'generated_outfit.png');

        if (data.text) {
            genText.textContent = data.text;
            genText.classList.add('visible');
        }

        if (data.prompt) {
            promptContent.textContent = data.prompt;
            promptDebug.classList.add('visible');
        }

        showStatus('success', 'Image generated successfully!');

        // Smooth scroll to result
        generatedDisplay.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Highlight glow effect
        generatedDisplay.parentElement.classList.add('highlight-result');
        setTimeout(() => {
            generatedDisplay.parentElement.classList.remove('highlight-result');
        }, 3000);

    } catch (err) {
        showStatus('error', `Generation failed: ${err.message}`);
        generatedDisplay.innerHTML = `
            <div class="output-placeholder">
                <div class="icon">❌</div>
                <p>Generation failed — try again</p>
            </div>`;
        console.error(err);
    } finally {
        generateBtn.disabled = false;
        generateBtn.classList.remove('loading');
    }
});

// Toggle prompt debug panel
function togglePrompt() {
    const content = document.getElementById('prompt-content');
    const toggle = document.getElementById('prompt-toggle');
    content.classList.toggle('visible');
    toggle.textContent = content.classList.contains('visible')
        ? '🔍 Hide Generation Prompt'
        : '🔍 View Generation Prompt';
}

// ---------------------------------------------------------------
// Render JSON Details — Syntax Highlighted
// ---------------------------------------------------------------

function renderDetails(details) {
    detailsPanel.innerHTML = renderJsonValue(details, 0);
}

function renderJsonValue(value, indent) {
    const pad = '  '.repeat(indent);
    const padInner = '  '.repeat(indent + 1);

    if (value === null || value === undefined) {
        return `<span class="json-null">null</span>`;
    }

    if (Array.isArray(value)) {
        if (value.length === 0) return `<span class="json-bracket">[]</span>`;
        const items = value.map((item, i) => {
            const comma = i < value.length - 1 ? ',' : '';
            return `${padInner}${renderJsonValue(item, indent + 1)}${comma}`;
        });
        return `<span class="json-bracket">[</span>\n${items.join('\n')}\n${pad}<span class="json-bracket">]</span>`;
    }

    if (typeof value === 'object') {
        const keys = Object.keys(value);
        if (keys.length === 0) return `<span class="json-bracket">{}</span>`;
        const entries = keys.map((key, i) => {
            const comma = i < keys.length - 1 ? ',' : '';
            return `${padInner}<span class="json-key">"${key}"</span>: ${renderJsonValue(value[key], indent + 1)}${comma}`;
        });
        return `<span class="json-bracket">{</span>\n${entries.join('\n')}\n${pad}<span class="json-bracket">}</span>`;
    }

    if (typeof value === 'number' || typeof value === 'boolean') {
        return `<span class="json-number">${value}</span>`;
    }

    // String — detect hex colors and add inline swatches
    const escaped = String(value).replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const withSwatches = escaped.replace(/(#[0-9A-Fa-f]{6})/g,
        '<span class="color-swatch" style="background:$1"></span>$1');
    return `<span class="json-string">"${withSwatches}"</span>`;
}

// ---------------------------------------------------------------
// Download Image
// ---------------------------------------------------------------

function downloadImage(dataUrl, filename) {
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}
