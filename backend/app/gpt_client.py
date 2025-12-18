# --- All imports at the top (PEP8 best practice) ---
import os
import json
from typing import Tuple, Optional, Dict, Any, Callable
import requests
import time
import random
import logging
import contextvars
from urllib.parse import urlparse
from dotenv import load_dotenv
from .config import (
    GPT_PROMPTS, ENV_PATH, DEFAULT_GPT_MODEL, GPT_MODELS,
    DEFAULT_TEMPERATURE, DEFAULT_TOP_P, DEFAULT_CHUNK_SIZE, TEXT_OVERLAP, MAX_OUTPUT_TOKENS,
    LLM_PROVIDER, AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION, AZURE_OPENAI_DEPLOYMENTS, DATAIKU_API_BASE,
    DATAIKU_API_KEY, DATAIKU_SERVICE_ID, DATAIKU_ENDPOINT_ID, DATAIKU_TIMEOUT, DATAIKU_CATALOG_MAP,
    DATAIKU_VERIFY_SSL, DATAIKU_CA_BUNDLE, DATAIKU_DSS_HOST,
    DATAIKU_DSS_HOST_IP, DATAIKU_DSS_API_KEY, DATAIKU_DSS_PROJECT, LOG_GPT_REQUESTS,
    LOG_GPT_PROMPTS, LOG_GPT_MAX_PROMPT_CHARS, LOG_GPT_MAX_RESPONSE_CHARS, LOG_GPT_SAMPLE_RATE, GPT_CALLS_LOG_PATH, LOG_GPT_INCLUDE_HEADERS,
    LOG_GPT_HEADER_WHITELIST, HTTP_REQUEST_TIMEOUT
)

# --- Certificate handling: Only use if file actually exists ---
# Check early before any API calls - this must happen at module import time
_ACTUAL_CA_BUNDLE = None
if DATAIKU_CA_BUNDLE:
    if os.path.isfile(DATAIKU_CA_BUNDLE):
        _ACTUAL_CA_BUNDLE = DATAIKU_CA_BUNDLE
        os.environ["REQUESTS_CA_BUNDLE"] = DATAIKU_CA_BUNDLE
        logging.info(f"Using corporate CA bundle: {DATAIKU_CA_BUNDLE}")
    else:
        logging.warning(f"CA bundle specified but file not found: {DATAIKU_CA_BUNDLE} - will use system CAs")
        _ACTUAL_CA_BUNDLE = DATAIKU_VERIFY_SSL  # Fall back to boolean True/False
else:
    _ACTUAL_CA_BUNDLE = DATAIKU_VERIFY_SSL

# --- DNS Fallback (Global - applied once at module import) ---
# Install DNS fallback BEFORE any threads start to ensure all workers use it
if DATAIKU_DSS_HOST_IP and DATAIKU_DSS_HOST:
    try:
        import socket
        from urllib.parse import urlparse
        _dns_fallback_hostname = urlparse(DATAIKU_DSS_HOST).hostname
        if _dns_fallback_hostname:
            _original_getaddrinfo = socket.getaddrinfo
            # Exclude internal Docker hostnames from custom DNS to avoid breaking Redis/Postgres connections
            _internal_hostnames = {'redis', 'postgres', 'dns-cache', 'backend', 'frontend', 'localhost', '127.0.0.1'}
            def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
                # Skip custom DNS for internal Docker services
                if host and host.lower() in _internal_hostnames:
                    return _original_getaddrinfo(host, port, family, type, proto, flags)
                # Use hardcoded IP for Dataiku host
                if host == _dns_fallback_hostname:
                    return _original_getaddrinfo(DATAIKU_DSS_HOST_IP, port, family, type, proto, flags)
                return _original_getaddrinfo(host, port, family, type, proto, flags)
            socket.getaddrinfo = _custom_getaddrinfo
            logging.info(f"[DNS_FALLBACK] Globally installed DNS override: {_dns_fallback_hostname} -> {DATAIKU_DSS_HOST_IP} (excluding internal services)")
    except Exception as dns_err:
        logging.warning(f"[DNS_FALLBACK] Failed to install global DNS resolver: {dns_err}")

# Module-level cache for persistent clients/handles to reduce DNS/connect overhead
_DSS_CACHE: Dict[str, Any] = {"client": None, "project": None, "llm": {}}

# --- Lightweight structured logger for GPT calls (opt-in) ---
_gpt_logger: Optional[logging.Logger] = None
_gpt_logger_ready: bool = False
if LOG_GPT_REQUESTS:
    try:
        os.makedirs(os.path.dirname(GPT_CALLS_LOG_PATH), exist_ok=True)
        _gpt_logger = logging.getLogger("gpt_calls")
        _gpt_logger.setLevel(logging.INFO)
        # Avoid duplicate handlers if module reloaded
        if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', '') == GPT_CALLS_LOG_PATH for h in _gpt_logger.handlers):
            fh = logging.FileHandler(GPT_CALLS_LOG_PATH, encoding='utf-8')
            fh.setLevel(logging.INFO)
            formatter = logging.Formatter('%(message)s')
            fh.setFormatter(formatter)
            _gpt_logger.addHandler(fh)
        # Force a startup log line (bypass sampling) to verify path/permissions
        try:
            _gpt_logger.info(json.dumps({
                "ts": time.time(),
                "phase": "startup",
                "message": "gpt logging initialized",
                "path": GPT_CALLS_LOG_PATH,
            }))
            _gpt_logger_ready = True
        except Exception:
            _gpt_logger_ready = False
    except Exception:
        _gpt_logger = None
        _gpt_logger_ready = False

# Per-thread/task logging context (e.g., job_id, extractor)
_gpt_log_ctx: contextvars.ContextVar = contextvars.ContextVar("gpt_log_ctx", default={})

def set_gpt_log_context(**kwargs):
    try:
        cur = dict(_gpt_log_ctx.get() or {})
        cur.update({k: v for k, v in kwargs.items() if v is not None})
        _gpt_log_ctx.set(cur)
    except Exception:
        pass

def clear_gpt_log_context():
    try:
        _gpt_log_ctx.set({})
    except Exception:
        pass

def _maybe_log_event(event: Dict[str, Any]):
    """Write a single JSON line event if GPT logging is enabled and sampling criteria met."""
    if not LOG_GPT_REQUESTS or _gpt_logger is None:
        return
    try:
        # Attach context (job_id, extractor, etc.) if present
        ctx = _gpt_log_ctx.get() or {}
        if isinstance(ctx, dict):
            for k in ("job_id", "extractor", "round_id"):
                if k in ctx and k not in event:
                    event[k] = ctx.get(k)
        # basic reservoir sampling via probability threshold
        if LOG_GPT_SAMPLE_RATE < 1.0 and random.random() > LOG_GPT_SAMPLE_RATE:
            return
        _gpt_logger.info(json.dumps(event, ensure_ascii=False))
    except Exception:
        pass

def gpt_logging_status() -> Dict[str, Any]:
    """Return current GPT logging status for diagnostics."""
    return {
        "enabled": bool(LOG_GPT_REQUESTS),
        "path": GPT_CALLS_LOG_PATH,
        "logger_ready": bool(_gpt_logger_ready and _gpt_logger is not None),
    }

def log_gpt_event(tag: str, extra: Optional[Dict[str, Any]] = None):
    """Emit a manual event to the GPT log (bypassing sampling)."""
    if not LOG_GPT_REQUESTS or _gpt_logger is None:
        return
    try:
        payload = {"ts": time.time(), "phase": tag}
        if isinstance(extra, dict):
            payload.update(extra)
        # include context if available
        ctx = _gpt_log_ctx.get() or {}
        if isinstance(ctx, dict):
            for k in ("job_id", "extractor", "round_id"):
                if k in ctx and k not in payload:
                    payload[k] = ctx.get(k)
        _gpt_logger.info(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass

def _redact(text: str, max_len: int) -> str:
    try:
        if not text:
            return text
        # simple email redaction
        import re
        text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<redacted-email>", text)
        if len(text) > max_len:
            return text[:max_len] + "…"
        return text
    except Exception:
        return text[:max_len] + "…"

def load_api_key():
    load_dotenv(ENV_PATH)
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in .env file.")
    return api_key

def chunk_text(text, chunk_size=DEFAULT_CHUNK_SIZE, overlap=TEXT_OVERLAP):
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunks.append(text[start:end])
        if end == text_length:
            break
        start = end - overlap  # overlap for context
    return chunks

def run_gpt_inquiry(prompt_key, input_file=None, model=DEFAULT_GPT_MODEL, temperature=DEFAULT_TEMPERATURE, top_p=DEFAULT_TOP_P):
    if prompt_key not in GPT_PROMPTS:
        raise ValueError(f"Prompt '{prompt_key}' not found in config.")
    with open(input_file, 'r', encoding='utf-8') as f:
        file_text = f.read()
    # Get model-specific chunk size and overlap if available
    model_settings = GPT_MODELS.get(model, {})
    chunk_size = model_settings.get('chunk_size', DEFAULT_CHUNK_SIZE)
    overlap = model_settings.get('overlap', TEXT_OVERLAP)
    chunks = chunk_text(file_text, chunk_size, overlap)
    prompt_template = GPT_PROMPTS[prompt_key]
    responses = []
    for i, chunk in enumerate(chunks):
        prompt = f"{prompt_template}\n\nReport Text (part {i+1}/{len(chunks)}):\n{chunk}"
        responses.append(_chat_completion(prompt, prompt_key, override_model=model,
                                          override_temperature=temperature, override_top_p=top_p))
    return "\n\n---\n\n".join(responses)

def gpt_extract(prompt, extractor_name, override_model=None):
    return _chat_completion(prompt, extractor_name, override_model=override_model)


# --- Provider implementations ---
def _with_retries(func, *, retries: int = 3, base_delay_seconds: float = 1.0, on_retry: Optional[Callable[[int, float, Exception], None]] = None):
    last_exc = None
    for attempt in range(retries):
        try:
            return func()
        except (requests.exceptions.RequestException, Exception) as exc:  # Broad by design; last attempt re-raises
            last_exc = exc
            
            # Log errors explicitly for visibility
            exc_type = type(exc).__name__
            if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout)):
                logging.error(f"[GPT_TIMEOUT] Request timed out on attempt {attempt + 1}/{retries}: {exc}")
            else:
                logging.error(f"[GPT_ERROR] {exc_type} on attempt {attempt + 1}/{retries}: {exc}")
            
            # Update job status to show GPT service warning for ALL errors
            try:
                ctx = _gpt_log_ctx.get() or {}
                job_id = ctx.get("job_id")
                if job_id:
                    import redis
                    redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)
                    job_json = redis_client.get(f"job:{job_id}")
                    if job_json:
                        import json
                        job_data = json.loads(job_json)
                        original_status = job_data.get("status", "")
                        # Extract readable error message
                        error_msg = str(exc)
                        if "502 Bad Gateway" in error_msg:
                            error_msg = "502 Bad Gateway (service unavailable)"
                        elif "timeout" in error_msg.lower():
                            error_msg = "Request timeout"
                        else:
                            error_msg = exc_type
                        job_data["status"] = f"⚠️ GPT service error: {error_msg} (retry {attempt + 1}/{retries}). {original_status}"
                        job_data["gpt_service_warning"] = True
                        redis_client.set(f"job:{job_id}", json.dumps(job_data), ex=86400)
            except Exception as status_err:
                logging.warning(f"Could not update job status for GPT error: {status_err}")
                    
            if attempt == retries - 1:
                break
            sleep_seconds = base_delay_seconds * (2 ** attempt) + random.uniform(0, 0.25)
            try:
                if callable(on_retry):
                    on_retry(attempt + 1, sleep_seconds, exc)
            except Exception:
                pass
            time.sleep(sleep_seconds)
    raise last_exc

def _call_openai(messages, model, max_tokens, temperature, top_p) -> Tuple[str, Optional[Any]]:
    # Lazy import so the openai package is only required when provider=openai
    import openai
    openai.api_key = load_api_key()
    response = _with_retries(lambda: openai.chat.completions.create(
            model=model,
        messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        top_p=top_p,
    ))
    content = response.choices[0].message.content
    usage = getattr(response, "usage", None)
    return content, usage


def _call_azure(messages, model, max_tokens, temperature, top_p) -> Tuple[str, Optional[Dict[str, Any]]]:
    deployment = AZURE_OPENAI_DEPLOYMENTS.get(model) or model
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{deployment}/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"
    headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }
    t0 = time.time()
    def _retry_cb(attempt, delay, exc):
        _maybe_log_event({
            "ts": time.time(),
            "phase": "retry",
            "provider": "azure",
            "model": model,
            "attempt": attempt,
            "next_delay_s": round(delay, 3),
            "error": str(exc),
        })
    r = _with_retries(lambda: requests.post(url, headers=headers, json=payload, timeout=HTTP_REQUEST_TIMEOUT), on_retry=_retry_cb)
    r.raise_for_status()
    # Log limited response headers for rate-limit diagnostics
    try:
        if LOG_GPT_REQUESTS and LOG_GPT_INCLUDE_HEADERS:
            hdrs = {}
            for k, v in (r.headers or {}).items():
                lk = str(k).lower()
                if lk in [h.lower() for h in LOG_GPT_HEADER_WHITELIST]:
                    hdrs[lk] = v
            _maybe_log_event({
                "ts": time.time(),
                "phase": "http",
                "provider": "azure",
                "model": model,
                "status_code": r.status_code,
                "duration_ms": int((time.time() - t0) * 1000),
                "headers": hdrs or None,
            })
    except Exception:
        pass
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage")
    return content, usage


def _call_dataiku_apinode(messages, model, max_tokens, temperature, top_p) -> Tuple[str, Optional[Dict[str, Any]]]:
    # Prefer official Dataiku API Python client when available
    payload = {
        "messages": messages,
        "params": {
            "model": DATAIKU_CATALOG_MAP.get(model, model),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
    }
    try:
        from dataikuapi import APINodeClient
        # Bind client to the service; then call run_function(endpoint_id, payload)
        client = APINodeClient(DATAIKU_API_BASE, DATAIKU_API_KEY, DATAIKU_SERVICE_ID)
        def _retry_cb(attempt, delay, exc):
            _maybe_log_event({
                "ts": time.time(),
                "phase": "retry",
                "provider": "dataiku_apinode",
                "model": model,
                "attempt": attempt,
                "next_delay_s": round(delay, 3),
                "error": str(exc),
            })
        resp = _with_retries(lambda: client.run_function(DATAIKU_ENDPOINT_ID, payload), on_retry=_retry_cb)
        content = (
            (resp.get("choices") or [{}])[0].get("message", {}).get("content")
            or resp.get("result")
            or resp.get("output")
            or resp.get("text")
            or ""
        )
        return content, resp.get("usage")
    except Exception:
        headers = {"X-API-Key": DATAIKU_API_KEY, "Content-Type": "application/json"}
        # Try common API Node function endpoint path
        url = f"{DATAIKU_API_BASE}/services/{DATAIKU_SERVICE_ID}/endpoints/{DATAIKU_ENDPOINT_ID}/run"
        verify_arg = _ACTUAL_CA_BUNDLE  # Use the validated CA bundle or fallback
        t0 = time.time()
        def _retry_cb2(attempt, delay, exc):
            _maybe_log_event({
                "ts": time.time(),
                "phase": "retry",
                "provider": "dataiku_apinode",
                "model": model,
                "attempt": attempt,
                "next_delay_s": round(delay, 3),
                "error": str(exc),
            })
        r = _with_retries(lambda: requests.post(url, headers=headers, json=payload, timeout=DATAIKU_TIMEOUT, verify=verify_arg), on_retry=_retry_cb2)
        try:
            if LOG_GPT_REQUESTS and LOG_GPT_INCLUDE_HEADERS:
                hdrs = {}
                for k, v in (r.headers or {}).items():
                    lk = str(k).lower()
                    if lk in [h.lower() for h in LOG_GPT_HEADER_WHITELIST]:
                        hdrs[lk] = v
                _maybe_log_event({
                    "ts": time.time(),
                    "phase": "http",
                    "provider": "dataiku_apinode",
                    "model": model,
                    "status_code": r.status_code,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "headers": hdrs or None,
                })
        except Exception:
            pass
        r.raise_for_status()
        data = r.json()
        content = (
            (data.get("choices") or [{}])[0].get("message", {}).get("content")
            or data.get("result")
            or data.get("output")
            or data.get("text")
            or ""
        )
        return content, data.get("usage")


def _call_dataiku_dss(messages, model, max_tokens, temperature, top_p) -> Tuple[str, Optional[Dict[str, Any]]]:
    # Use Dataiku DSS Python client, LLM catalog, with connection caching
    from dataikuapi import DSSClient
    # CA bundle and DNS fallback applied globally at module import time (see top of file)
    
    # Log that we're using DNS fallback for this call if configured
    if DATAIKU_DSS_HOST_IP and DATAIKU_DSS_HOST:
        _maybe_log_event({
            "ts": time.time(),
            "phase": "dns_fallback",
            "provider": "dataiku_dss",
            "hostname": urlparse(DATAIKU_DSS_HOST).hostname,
            "ip": DATAIKU_DSS_HOST_IP,
        })
    
    # Create/cache client and project
    if _DSS_CACHE["client"] is None:
        _DSS_CACHE["client"] = DSSClient(DATAIKU_DSS_HOST, DATAIKU_DSS_API_KEY, no_check_certificate=(not DATAIKU_VERIFY_SSL))
    if _DSS_CACHE["project"] is None:
        _DSS_CACHE["project"] = _DSS_CACHE["client"].get_project(DATAIKU_DSS_PROJECT)
    project = _DSS_CACHE["project"]
    llm_id = DATAIKU_CATALOG_MAP.get(model, model)
    llm = _DSS_CACHE["llm"].get(llm_id)
    if llm is None:
        llm = project.get_llm(llm_id)
        _DSS_CACHE["llm"][llm_id] = llm
    comp = llm.new_completion()
    # Optional system prompt
    comp = comp.with_message("You are a helpful assistant.", "system")
    # User message from our prompt
    comp = comp.with_message(messages[0]["content"])  # assumes single user message
    # If the SDK supports params tuning, it would be something like:
    # comp = comp.with_params(max_tokens=max_tokens, temperature=temperature, top_p=top_p)
    def _retry_cb(attempt, delay, exc):
        _maybe_log_event({
            "ts": time.time(),
            "phase": "retry",
            "provider": "dataiku_dss",
            "model": model,
            "attempt": attempt,
            "next_delay_s": round(delay, 3),
            "error": str(exc),
        })
    t0 = time.time()
    
    # Note: We rely on the Dataiku SDK's internal timeout mechanisms.
    # signal.alarm() doesn't work in worker threads, so we removed it.
    # The DNS fallback above helps avoid long DNS resolution hangs.
    resp = _with_retries(lambda: comp.execute(), on_retry=_retry_cb)
    
    try:
        # SDK doesn't expose headers; still log latency to detect server-side slowness
        _maybe_log_event({
            "ts": time.time(),
            "phase": "http",
            "provider": "dataiku_dss",
            "model": model,
            "status_code": None,
            "duration_ms": int((time.time() - t0) * 1000),
            "headers": None,
        })
    except Exception:
        pass
    text = getattr(resp, 'text', None)
    if text is None:
        # Fallback if SDK returns dict
        try:
            data = resp if isinstance(resp, dict) else resp.__dict__
            text = data.get('text') or data.get('result') or ''
        except Exception:
            text = ''
    return text, None


def _chat_completion(prompt: str, extractor_name: str, *, override_model: Optional[str] = None,
                     override_temperature: Optional[float] = None, override_top_p: Optional[float] = None) -> str:
    from .gpt_tracker import track_gpt_call
    from .config import get_runtime_model_config
    model = override_model or get_runtime_model_config(extractor_name)
    # Use values from .env via config constants
    max_tokens = MAX_OUTPUT_TOKENS
    temperature = override_temperature if override_temperature is not None else DEFAULT_TEMPERATURE
    top_p = override_top_p if override_top_p is not None else DEFAULT_TOP_P
    messages = [{"role": "user", "content": prompt}]

    t0 = time.time()
    provider = LLM_PROVIDER
    # Set extractor into log context for downstream provider logs
    try:
        set_gpt_log_context(extractor=extractor_name)
    except Exception:
        pass
    # Pre-call log (metadata only; optional prompt excerpt)
    try:
        if LOG_GPT_REQUESTS:
            _maybe_log_event({
                "ts": time.time(),
                "phase": "request",
                "extractor": extractor_name,
                "provider": provider,
                "model": model,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "prompt_chars": len(prompt or ""),
                "prompt_excerpt": _redact(prompt, LOG_GPT_MAX_PROMPT_CHARS) if LOG_GPT_PROMPTS else None,
            })
    except Exception:
        pass

    try:
        if provider == "azure":
            content, usage = _call_azure(messages, model, max_tokens, temperature, top_p)
        elif provider == "dataiku_apinode":
            content, usage = _call_dataiku_apinode(messages, model, max_tokens, temperature, top_p)
        elif provider == "dataiku_dss":
            content, usage = _call_dataiku_dss(messages, model, max_tokens, temperature, top_p)
        else:
            content, usage = _call_openai(messages, model, max_tokens, temperature, top_p)
    except Exception as e:
        # Failure log
        try:
            if LOG_GPT_REQUESTS:
                _maybe_log_event({
                    "ts": time.time(),
                    "phase": "error",
                    "extractor": extractor_name,
                    "provider": provider,
                    "model": model,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": str(e),
                })
        except Exception:
            pass
        raise

    duration = time.time() - t0

    # Normalize common markdown fences for downstream JSON parsers
    if isinstance(content, str):
        cleaned = content.strip()
        if cleaned.startswith('```'):
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            else:
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            content = cleaned.strip()

    # Optional usage tracking if available
    try:
        if usage and isinstance(usage, dict):
            track_gpt_call(
                model=model,
                prompt_tokens=usage.get('prompt_tokens'),
                completion_tokens=usage.get('completion_tokens'),
                extractor_name=extractor_name,
                duration_seconds=None,
            )
    except Exception:
        pass

    # Post-call success log
    try:
        if LOG_GPT_REQUESTS:
            _maybe_log_event({
                "ts": time.time(),
                "phase": "response",
                "extractor": extractor_name,
                "provider": provider,
                "model": model,
                "duration_ms": int(duration * 1000),
                "usage": usage if isinstance(usage, dict) else None,
                "response_chars": len(content or "") if isinstance(content, str) else None,
                "response_excerpt": _redact(content, LOG_GPT_MAX_RESPONSE_CHARS) if (LOG_GPT_PROMPTS and isinstance(content, str)) else None,
            })
    except Exception:
        pass
    return content

__all__ = [
    "gpt_extract",
    "run_gpt_inquiry",
    "load_api_key",
    "set_gpt_log_context",
    "clear_gpt_log_context",
    "gpt_logging_status",
    "log_gpt_event",
]

def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Run GPT inquiry on SOC 2 report text.")
    parser.add_argument('--prompt', type=str, help='Prompt key to use (see config.py)')
    parser.add_argument('--input', type=str, required=True, help='Input text file')
    parser.add_argument('--model', type=str, default=DEFAULT_GPT_MODEL, help='GPT model to use (see config.py)')
    parser.add_argument('--temperature', type=float, default=DEFAULT_TEMPERATURE, help='Sampling temperature')
    parser.add_argument('--top_p', type=float, default=DEFAULT_TOP_P, help='Nucleus sampling top_p')
    parser.add_argument('--analyze', action='store_true', help='Analyze SOC 2 report and estimate section positions')
    parser.add_argument('--section-candidates', action='store_true', help='Find section candidates with probability/confidence approach')
    import pathlib
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
    parser.add_argument('--json', type=str, default=str(PROJECT_ROOT / 'data/json/section_candidates.json'), help='Output JSON file for section candidates')
    args = parser.parse_args()

    if args.section_candidates:
        from .pdf_handler import find_section_candidates
        with open(args.input, 'r', encoding='utf-8') as f:
            text = f.read()
        print("Finding section candidates with probability/confidence approach...")
        results = find_section_candidates(text, args.model, args.temperature, args.top_p)
        for topic, candidates in results.items():
            print(f"\nSection: {topic}")
            for cand in candidates:
                print(f"  Offset: {cand['offset']} | Confidence: {cand['confidence']} | Indicators: {cand['indicators']}\n  Snippet: {cand['snippet'][:200]}\n---")
        # Save to JSON file
        os.makedirs(os.path.dirname(args.json), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8') as jf:
            json.dump(results, jf, indent=2)
        print(f"Section candidate results saved to {args.json}")
    elif args.analyze:
        from .pdf_handler import get_section_positions
        with open(args.input, 'r', encoding='utf-8') as f:
            text = f.read()
        total_chars = len(text)
        print(f"Total character count: {total_chars}")
        result = get_section_positions(text, args.model, args.temperature, args.top_p)
        print("\nSection positions and confidence:")
        print(result)
    else:
        if not args.prompt:
            raise ValueError("Prompt key is required unless --analyze or --section-candidates is used.")
        result = run_gpt_inquiry(args.prompt, args.input, args.model, args.temperature, args.top_p)
        print("\nGPT Response:\n", result)

if __name__ == "__main__":
    main()
