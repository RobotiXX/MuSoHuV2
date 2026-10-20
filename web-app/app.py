"""
MuSoHu Web Application
Manages ROS2 scripts, displays logs, and monitors system resources
"""
from fastapi import FastAPI, Request, Query, Body
from starlette.concurrency import run_in_threadpool
from process_manager import ProcessManager
from clock_sync import ClockSync
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import shutil
import logging
from datetime import datetime
import yaml
from file_discovery import FileDiscoveryService

# Get the base directory of this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Setup logger first
logger = logging.getLogger("uvicorn")

# Prepare paths
static_dir = os.path.join(BASE_DIR, "static")
templates_dir = os.path.join(BASE_DIR, "templates")

if not os.path.exists(static_dir):
    logger.error(f"Static directory not found: {static_dir}")
if not os.path.exists(templates_dir):
    logger.error(f"Templates directory not found: {templates_dir}")

# Initialize FastAPI app
app = FastAPI()

# Add middleware FIRST
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates
templates = Jinja2Templates(directory=templates_dir)
logger.info(f"Templates directory: {templates_dir}")

# Mount static files LAST - this is critical for proper route registration
try:
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"Successfully mounted static files from: {static_dir}")
except Exception as e:
    logger.error(f"Failed to mount static files: {e}")

# Load configuration
def load_config():
    """Load configuration from config.yml"""
    config_path = os.environ.get('MUSOHU_CONFIG', os.path.join(BASE_DIR, 'config.yml'))
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config.yml: {e}")
            return get_default_config()
    else:
        logger.warning("config.yml not found, using default configuration")
        return get_default_config()

def get_default_config():
    """Return default configuration"""
    return {
        'log_viewer': {
            'max_lines': 100,
            'scan_directories': [],
            'sources': [],
            'allowed_extensions': ['.log', '.txt']
        },
        'server': {
            'host': '0.0.0.0',
            'port': 8000
        },
        'refresh_intervals': {
            'scripts': 5,
            'disk_space': 10,
            'logs': 5
        }
    }

# Load configuration
config = load_config()

# Initialize file discovery service
file_discovery = FileDiscoveryService(config)

# Resolve user log paths independently of the service working directory.
for collection in (config.get('log_dirs', []), config.get('log_viewer', {}).get('scan_directories', [])):
    for entry in collection:
        if 'path' in entry:
            entry['path'] = os.path.expanduser(os.path.expandvars(entry['path']))
manager = ProcessManager(BASE_DIR, config)
clock_sync = ClockSync(manager)

@app.on_event("shutdown")
async def stop_owned_processes():
    await run_in_threadpool(manager.close)

# ---------------------------- Page Routes -----------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page - Scripts management"""
    refresh_interval = config.get('refresh_intervals', {}).get('scripts', 5)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "refresh_interval": refresh_interval
    })


@app.get("/disk-space", response_class=HTMLResponse)
async def disk_space(request: Request):
    """Disk space monitoring page"""
    refresh_interval = config.get('refresh_intervals', {}).get('disk_space', 10)
    return templates.TemplateResponse("disk_space.html", {
        "request": request,
        "refresh_interval": refresh_interval
    })


@app.get("/logs", response_class=HTMLResponse)
async def logs(request: Request):
    """Log viewer page"""
    refresh_interval = config.get('refresh_intervals', {}).get('logs', 5)
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "refresh_interval": refresh_interval
    })


# ============================================================================
# API Routes - Health Check
# ----------------------- API Routes - Health Check --------------------------
@app.get("/api/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return JSONResponse(content={
        'status': 'healthy',
        'running_scripts': sum(item.get('pid') is not None for item in manager.status().values()),
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# API Routes - Scripts
# ============================================================================

# ------------------------- API Routes - Scripts -----------------------------

@app.get("/api/scripts")
async def list_scripts():
    """List all available ROS2 scripts and their status"""
    return JSONResponse(content=manager.status())


@app.get("/api/recording/config")
async def recording_config():
    return JSONResponse(content=manager.defaults())


@app.get("/api/time")
async def system_time():
    return JSONResponse(content=await run_in_threadpool(clock_sync.status))


@app.post("/api/time/sync")
async def sync_phone_time(payload: dict = Body(default={})):
    try:
        state = await run_in_threadpool(clock_sync.change, epoch_ms=payload.get('epoch_ms'))
        return JSONResponse(content=state, status_code=200 if state['last_result']['lidar_ready'] else 503)
    except ValueError as exc:
        return JSONResponse(content={'error': str(exc)}, status_code=409)
    except (RuntimeError, subprocess.SubprocessError) as exc:
        return JSONResponse(content={'error': str(exc)}, status_code=503)


@app.post("/api/time/internet")
async def enable_internet_time():
    try:
        return JSONResponse(content=await run_in_threadpool(clock_sync.change, internet=True))
    except ValueError as exc:
        return JSONResponse(content={'error': str(exc)}, status_code=409)
    except (RuntimeError, subprocess.SubprocessError) as exc:
        return JSONResponse(content={'error': str(exc)}, status_code=503)


# -------------------- API Routes - System Monitoring -----------------------

@app.get("/api/disk-space")
async def get_disk_space():
    """Get disk space information"""
    try:
        # Use df command to get accurate disk usage (matches df -h output)
        # This accounts for filesystem overhead and reserved blocks
        result = subprocess.run(
            ['df', '-h', '/'],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse df output
        # Output format: Filesystem Size Used Avail Use% Mounted
        lines = result.stdout.strip().split('\n')
        if len(lines) < 2:
            raise Exception("Unexpected df output format")
        
        # Get the data line (skip header)
        data_line = lines[1].split()
        
        # Extract values (handling different df output formats)
        if len(data_line) >= 5:
            total = data_line[1]      # Size
            used = data_line[2]       # Used
            free = data_line[3]       # Available
            percent_used = data_line[4]  # Use%
            
            disk_info = {
                'total': total,
                'used': used,
                'free': free,
                'percent_used': percent_used
            }
            
            return JSONResponse(content=disk_info)
        else:
            raise Exception("Could not parse df output")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"df command failed: {e}")
        return JSONResponse(content={'error': 'Failed to get disk space information'}, status_code=500)
    except Exception as e:
        logger.error(f"Error getting disk space: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)

@app.get("/api/logs")
async def get_logs(source: str = Query(default="musohu", alias="source")):
    """Legacy logs endpoint: return last N lines from a selected log source.

    Supports:
    - File-based logs discovered from configured scan directories or explicit sources
    - System journal logs when log_dirs entry has type: journalctl
    """
    try:
        log_source = source
        log_viewer_config = config.get('log_viewer', {})
        max_lines = int(log_viewer_config.get('max_lines', 100))

        # Check if this is a journalctl source via log_dirs config
        log_dirs = config.get('log_dirs', [])
        journal_entry = next((d for d in log_dirs if d.get('key') == log_source and d.get('type') == 'journalctl'), None)
        if journal_entry is not None:
            try:
                result = subprocess.run(
                    ['journalctl', '-n', str(max_lines), '--no-pager', '--output=short-iso'],
                    capture_output=True, text=True, check=True
                )
                lines = [ln for ln in result.stdout.strip().split('\n') if ln]
                logs = []
                for line in lines:
                    parts = line.split(' ', 2)
                    if len(parts) == 3:
                        timestamp, _host, rest = parts
                        logs.append({'timestamp': timestamp, 'level': 'INFO', 'message': rest})
                    else:
                        logs.append({'timestamp': '', 'level': 'INFO', 'message': line})
                return JSONResponse(content={'logs': logs, 'source': log_source})
            except Exception as e:
                logger.error(f'Error reading journalctl logs: {str(e)}')
                return JSONResponse(content={'logs': [], 'error': f'Error reading journalctl logs: {str(e)}'}, status_code=500)

        # Build file-based sources mapping
        log_files = {}

        # 1) Scan configured directories
        for dir_config in log_viewer_config.get('scan_directories', []):
            if not dir_config.get('enabled', True):
                continue
            dir_path = dir_config.get('path', '')
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                try:
                    for filename in os.listdir(dir_path):
                        file_path = os.path.join(dir_path, filename)
                        if os.path.isfile(file_path):
                            log_id = filename.replace('.', '_')
                            if log_id in log_files:
                                log_id = f"{os.path.basename(dir_path.rstrip('/'))}_{log_id}"
                            log_files[log_id] = file_path
                except Exception as e:
                    logger.error(f"Error scanning directory {dir_path}: {e}")

        # 2) Explicit sources (optional)
        for src in log_viewer_config.get('sources', []):
            if src.get('enabled', True):
                log_files[src['id']] = src['path']

        # 3) Fallback to local logs/ directory
        if not log_files:
            logs_dir = os.path.join(BASE_DIR, 'logs')
            if os.path.exists(logs_dir) and os.path.isdir(logs_dir):
                for filename in os.listdir(logs_dir):
                    file_path = os.path.join(logs_dir, filename)
                    if os.path.isfile(file_path):
                        log_id = filename.replace('.', '_')
                        log_files[log_id] = file_path

        # Resolve desired file path
        log_file = log_files.get(log_source)
        if not log_file:
            # Default to a common app log file
            candidate = os.path.join(BASE_DIR, 'logs', 'musohu.log')
            log_file = candidate if os.path.exists(candidate) else None

        if not log_file:
            return JSONResponse(content={'logs': [], 'error': 'Log file not found'}, status_code=404)

        # Validate extension
        allowed_extensions = log_viewer_config.get('allowed_extensions', ['.log', '.txt'])
        if os.path.splitext(log_file)[1] not in allowed_extensions:
            return JSONResponse(content={
                'logs': [],
                'error': f'Unable to display this file type. Only {", ".join(allowed_extensions)} files can be displayed.'
            }, status_code=400)

        # Read file and return last N lines
        logs = []
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                lines = lines[-max_lines:] if max_lines > 0 else lines
                for line in lines:
                    line = line.rstrip('\n')
                    if not line:
                        continue
                    # Try to parse "[timestamp] LEVEL: message" format; fall back otherwise
                    if '] ' in line:
                        parts = line.split('] ', 1)
                        timestamp = parts[0].replace('[', '')
                        rest = parts[1]
                        level = 'INFO'
                        message = rest
                        if ': ' in rest:
                            lvl, msg = rest.split(': ', 1)
                            level, message = lvl, msg
                        logs.append({'timestamp': timestamp, 'level': level, 'message': message})
                    else:
                        logs.append({'timestamp': '', 'level': 'INFO', 'message': line})
        except UnicodeDecodeError:
            return JSONResponse(content={
                'logs': [],
                'error': 'Unable to display this file. The file contains non-text or binary data.'
            }, status_code=400)
        except Exception as read_error:
            logger.error(f'Error reading file {log_file}: {str(read_error)}')
            return JSONResponse(content={'logs': [], 'error': f'Error reading file: {str(read_error)}'}, status_code=500)

        return JSONResponse(content={'logs': logs, 'source': log_source})
    except Exception as e:
        logger.error(f'Failed to read logs: {str(e)}')
        return JSONResponse(content={'error': str(e)}, status_code=500)


# --------------------- API Routes - Log Management -------------------------

@app.get("/api/logs/sources")
async def get_log_sources():
    """Get all available log sources"""
    sources = {}
    # Get scan directories from config
    log_viewer_config = config.get('log_viewer', {})
    scan_directories = log_viewer_config.get('scan_directories', [])

    # Scan each configured directory for ALL files
    for dir_config in scan_directories:
        if not dir_config.get('enabled', True):
            continue

        dir_path = dir_config.get('path', '')
        name_prefix = dir_config.get('name_prefix', '')

        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            try:
                for filename in sorted(os.listdir(dir_path)):
                    file_path = os.path.join(dir_path, filename)
                    # Skip directories, only include files
                    if os.path.isfile(file_path):
                        # Create unique ID from filename
                        log_id = filename.replace('.', '_')
                        # If there's a collision, add directory name to make it unique
                        if log_id in sources:
                            log_id = f"{os.path.basename(dir_path.rstrip('/'))}_{log_id}"

                        # Create display name
                        display_name = f"{name_prefix}{filename}"

                        sources[log_id] = {
                            'name': display_name,
                            'path': file_path,
                            'exists': True
                        }
            except Exception as e:
                logger.error(f"Error scanning directory {dir_path}: {e}")

    # Add individual sources from config (for files outside scan directories)
    sources_config = log_viewer_config.get('sources', [])
    for source in sources_config:
        if source.get('enabled', True):
            sources[source['id']] = {
                'name': source['name'],
                'path': source['path'],
                'exists': os.path.exists(source['path'])
            }

    # Fallback: scan logs/ folder if no config
    if not sources:
        logs_dir = 'logs'
        if os.path.exists(logs_dir) and os.path.isdir(logs_dir):
            for filename in sorted(os.listdir(logs_dir)):
                file_path = os.path.join(logs_dir, filename)
                if os.path.isfile(file_path):
                    log_id = filename.replace('.', '_')
                    sources[log_id] = {
                        'name': filename,
                        'path': file_path,
                        'exists': True
                    }

    return JSONResponse(content=sources)

@app.get("/api/logs/download")
async def download_log(source: str = Query(default="", alias="source")):
    """Download a log file"""
    try:
        log_source = source
        log_viewer_config = config.get('log_viewer', {})

        # Build log files mapping by scanning directories
        log_files = {}
        scan_directories = log_viewer_config.get('scan_directories', [])

        for dir_config in scan_directories:
            if not dir_config.get('enabled', True):
                continue

            dir_path = dir_config.get('path', '')

            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                try:
                    for filename in os.listdir(dir_path):
                        file_path = os.path.join(dir_path, filename)
                        # Only include files, not directories
                        if os.path.isfile(file_path):
                            log_id = filename.replace('.', '_')
                            # Handle ID collisions
                            if log_id in log_files:
                                log_id = f"{os.path.basename(dir_path.rstrip('/'))}_{log_id}"
                            log_files[log_id] = (file_path, filename)
                except Exception as e:
                    logger.error(f"Error scanning directory {dir_path}: {e}")

        # Add individual sources from config
        sources = log_viewer_config.get('sources', [])
        for source in sources:
            if source.get('enabled', True):
                log_files[source['id']] = (source['path'], os.path.basename(source['path']))

        if log_source not in log_files:
            return JSONResponse(content={'error': 'Log file not found'}, status_code=404)

        log_file_path, original_filename = log_files[log_source]

        if not os.path.exists(log_file_path):
            return JSONResponse(content={'error': 'Log file not found on disk'}, status_code=404)

        logger.info(f'Downloading log file: {original_filename}')
        return FileResponse(
            log_file_path,
            media_type='application/octet-stream',
            filename=original_filename
        )
    except Exception as e:
        logger.error(f'Failed to download log: {str(e)}')
        return JSONResponse(content={'error': str(e)}, status_code=500)


# ============================================================================
# NEW API Routes - Enhanced Log Viewer
# ============================================================================

@app.get("/api/files")
async def list_files():
    """
    List all available log files with metadata
    Returns files grouped by directory
    """
    try:
        files_by_dir = file_discovery.get_files_by_directory()

        # Convert to response format
        response = {}
        for dir_key, files in files_by_dir.items():
            # Get directory description from first file
            dir_description = files[0].dir_description if files else dir_key

            response[dir_key] = {
                'description': dir_description,
                'files': [
                    {
                        'id': f"{file.dir_key}/{file.name}",
                        **file.to_dict()
                    }
                    for file in files
                ]
            }

        # Add virtual entries for journalctl sources so they appear in the UI
        log_dirs = config.get('log_dirs', [])
        for entry in log_dirs:
            if entry.get('type') == 'journalctl':
                dir_key = entry.get('key', 'system')
                dir_description = entry.get('description', 'Systemd Journal Logs')
                if dir_key not in response:
                    response[dir_key] = {
                        'description': dir_description,
                        'files': []
                    }
                # Add a pseudo-file representing journalctl output
                response[dir_key]['files'].append({
                    'id': f"{dir_key}/journalctl",
                    'name': 'journalctl',
                    'path': 'journalctl',
                    'dir_key': dir_key,
                    'dir_description': dir_description,
                    'size': 0,
                    'size_human': 'stream',
                    'modified_time': None,
                    'modified_time_human': None,
                    'exists': True,
                    'extension': '.log'
                })
        
        return JSONResponse(content=response)
    except Exception as e:
        logger.error(f'Failed to list files: {str(e)}')
        return JSONResponse(content={'error': str(e)}, status_code=500)


@app.get("/api/file")
async def get_file(
    file_id: str = Query(..., description="File ID in format: dir_key/filename"),
    lines: int = Query(None, description="Number of lines to return"),
    tail: bool = Query(True, description="Return last N lines (True) or first N lines (False)"),
    search: str = Query(None, description="Search term to filter lines")
):
    """
    Get file contents with optional search
    
    Query parameters:
    - file_id: Unique file identifier (dir_key/filename)
    - lines: Max number of lines to return (default from config)
    - tail: If true, return last N lines; else first N lines
    - search: Optional search term to filter results
    """
    try:
        # Handle virtual journalctl files: <dir_key>/journalctl
        try:
            dir_key, file_name = file_id.split('/', 1)
        except ValueError:
            dir_key, file_name = None, None

        if file_name == 'journalctl':
            # Determine default lines
            default_lines = config.get('server', {}).get('default_lines', 500)
            n = default_lines if lines is None else (lines if lines > 0 else default_lines)
            # Build journalctl command (tail or head equivalent by limiting lines)
            cmd = ['journalctl', '--no-pager', '--output=short-iso', '-n', str(n)]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                raw_lines = result.stdout.splitlines()
                if not tail and len(raw_lines) > n:
                    raw_lines = raw_lines[:n]
                return JSONResponse(content={
                    'file_id': file_id,
                    'metadata': {
                        'name': 'journalctl',
                        'path': 'journalctl',
                        'dir_key': dir_key or 'system',
                        'dir_description': 'Systemd Journal Logs',
                        'size_human': 'stream',
                        'exists': True
                    },
                    'lines': raw_lines,
                    'total_lines': len(raw_lines)
                })
            except Exception as e:
                logger.error(f'Failed to read journalctl: {e}')
                return JSONResponse(content={'error': f'Failed to read journalctl: {str(e)}'}, status_code=500)

        # If search is provided, use search functionality
        if search:
            search_config = config.get('log_viewer', {}).get('search', {})
            case_sensitive = search_config.get('case_sensitive', False)
            max_results = search_config.get('max_results', 1000)
            
            results = file_discovery.search_in_file(
                file_id, 
                search, 
                case_sensitive=case_sensitive,
                max_results=max_results
            )
            
            return JSONResponse(content={
                'file_id': file_id,
                'search_term': search,
                'results': results,
                'total_matches': len(results)
            })
        
        # Otherwise, return file contents
        file_lines = file_discovery.read_file_lines(file_id, max_lines=lines, tail=tail)
        
        if file_lines is None:
            return JSONResponse(
                content={'error': 'File not found'},
                status_code=404
            )
        
        # Get file metadata
        metadata = file_discovery.get_file_by_id(file_id)
        
        return JSONResponse(content={
            'file_id': file_id,
            'metadata': metadata.to_dict() if metadata else None,
            'lines': [line.rstrip('\n') for line in file_lines],
            'total_lines': len(file_lines)
        })
        
    except Exception as e:
        logger.error(f'Failed to get file {file_id}: {str(e)}')
        return JSONResponse(content={'error': str(e)}, status_code=500)


@app.get("/api/file/download")
async def download_file(
    file_id: str = Query(..., description="File ID in format: dir_key/filename")
):
    """Download a log file"""
    try:
        # Block downloads for journalctl virtual file
        if file_id.endswith('/journalctl'):
            return JSONResponse(content={'error': 'Download not supported for journalctl stream'}, status_code=400)
        metadata = file_discovery.get_file_by_id(file_id)
        
        if not metadata:
            return JSONResponse(
                content={'error': 'File not found'},
                status_code=404
            )
        
        if not metadata.exists:
            return JSONResponse(
                content={'error': 'File does not exist on disk'},
                status_code=404
            )
        
        logger.info(f'Downloading file: {metadata.name} from {metadata.dir_key}')
        return FileResponse(
            metadata.path,
            media_type='application/octet-stream',
            filename=metadata.name
        )
    except Exception as e:
        logger.error(f'Failed to download file {file_id}: {str(e)}')
        return JSONResponse(content={'error': str(e)}, status_code=500)


@app.get("/api/file/stream")
async def stream_file(
    file_id: str = Query(..., description="File ID in format: dir_key/filename")
):
    """
    Stream file contents (useful for large files)
    Returns file as a streaming response
    """
    try:
        # Block streaming for journalctl virtual file (use get_file instead)
        if file_id.endswith('/journalctl'):
            return JSONResponse(content={'error': 'Use /api/file for journalctl content'}, status_code=400)
        metadata = file_discovery.get_file_by_id(file_id)
        
        if not metadata or not metadata.exists:
            return JSONResponse(
                content={'error': 'File not found'},
                status_code=404
            )
        
        def generate():
            try:
                with open(metadata.path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        yield line
            except Exception as e:
                logger.error(f"Error streaming file {metadata.path}: {e}")
        
        return StreamingResponse(
            generate(),
            media_type='text/plain',
            headers={'Content-Disposition': f'inline; filename="{metadata.name}"'}
        )
    except Exception as e:
        logger.error(f'Failed to stream file {file_id}: {str(e)}')
        return JSONResponse(content={'error': str(e)}, status_code=500)


# ============================================================================
# API Routes - Scripts
# ============================================================================
@app.post("/api/scripts/{script_id}/start")
async def start_script(script_id: str, payload: dict = Body(default={})):
    if script_id == 'rviz2':
        script_id = 'record_bag'
    try:
        state = await run_in_threadpool(manager.start, script_id,
                                       payload.get('label', 'session'), payload.get('topics'))
        return JSONResponse(content=dict(state, message='Starting; waiting for recorder confirmation.'
                            if script_id == 'record_bag' else 'Sensor launch started.'), status_code=202)
    except KeyError:
        return JSONResponse(content={'error': 'Unknown operation'}, status_code=404)
    except ValueError as exc:
        return JSONResponse(content={'error': str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception('Unable to start %s', script_id)
        return JSONResponse(content={'error': str(exc)}, status_code=500)


@app.post("/api/scripts/{script_id}/stop")
async def stop_script(script_id: str):
    if script_id == 'rviz2':
        script_id = 'record_bag'
    if script_id not in ('record_bag', 'helmet_nodes'):
        return JSONResponse(content={'error': 'Unknown operation'}, status_code=404)
    try:
        state = await run_in_threadpool(manager.stop, script_id)
        return JSONResponse(content=dict(state, message='Recording finalized and stopped.'
                            if script_id == 'record_bag' and state.get('finalized') else
                            'Stop completed.'), status_code=500 if state.get('status') == 'failed' else 200)
    except Exception as exc:
        logger.exception('Unable to stop %s', script_id)
        return JSONResponse(content={'error': str(exc)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    server_config = config.get('server', {})
    host = server_config.get('host', '0.0.0.0')
    port = server_config.get('port', 8000)
    uvicorn.run("app:app", host=host, port=port, reload=False)

