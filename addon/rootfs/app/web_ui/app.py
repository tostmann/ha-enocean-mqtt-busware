"""
Web UI Application (Starlette)
Updated with Discovery API
"""
import os
import json
import logging
from starlette.applications import Starlette
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from service_state import service_state

logger = logging.getLogger(__name__)

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_PATH = os.path.join(BASE_PATH, 'templates')

async def homepage(request):
    try:
        # Use dashboard_new logic
        with open(os.path.join(TEMPLATES_PATH, 'dashboard_new.html'), 'r', encoding='utf-8') as f:
            content = f.read()
        return HTMLResponse(content)
    except Exception as e:
        return HTMLResponse(f"Error loading dashboard: {e}", status_code=500)

# --- API Endpoints ---

async def api_status(request):
    """Get service status including Discovery info"""
    status = service_state.get_status()
    
    # Add Discovery Status
    service = service_state.get_service()
    if service:
        status['discovery_active'] = service.is_discovery_active()
        status['discovery_remaining'] = service.get_discovery_time_remaining()
    else:
        status['discovery_active'] = False
        status['discovery_remaining'] = 0
        
    return JSONResponse(status)

async def api_discovery_control(request):
    """Start/Stop Discovery"""
    service = service_state.get_service()
    if not service:
        return JSONResponse({'error': 'Service not ready'}, status_code=503)
        
    if request.method == 'POST':
        try:
            data = await request.json()
            action = data.get('action') # 'start' or 'stop'
            
            if action == 'start':
                duration = int(data.get('duration', 60))
                service.start_discovery(duration)
                return JSONResponse({'status': 'started', 'duration': duration})
            elif action == 'stop':
                service.stop_discovery()
                return JSONResponse({'status': 'stopped'})
            else:
                return JSONResponse({'error': 'Invalid action'}, status_code=400)
        except Exception as e:
            return JSONResponse({'error': str(e)}, status_code=400)

async def api_devices(request):
    if request.method == 'GET':
        manager = service_state.get_device_manager()
        if not manager: return JSONResponse({'error': 'Service not ready'}, status_code=503)
        return JSONResponse({'devices': manager.list_devices()})
    
    elif request.method == 'POST':
        try:
            data = await request.json()
            manager = service_state.get_device_manager()
            if not manager: return JSONResponse({'error': 'Service not ready'}, status_code=503)
            
            success = manager.add_device(
                data.get('id'),
                data.get('name'),
                data.get('eep'),
                data.get('manufacturer', 'EnOcean')
            )
            # Update RORG if provided manually
            if success and data.get('rorg'):
                dev = manager.get_device(data.get('id'))
                if dev:
                    dev['rorg'] = data.get('rorg')
                    manager.save_devices()

            if success: return JSONResponse({'status': 'created'})
            else: return JSONResponse({'detail': 'Device ID already exists'}, status_code=400)
        except Exception as e: return JSONResponse({'detail': str(e)}, status_code=400)

async def api_device_detail(request):
    device_id = request.path_params['device_id']
    manager = service_state.get_device_manager()
    if not manager: return JSONResponse({'error': 'Service not ready'}, status_code=503)
    
    if request.method == 'GET':
        device = manager.get_device(device_id)
        if device: return JSONResponse(device)
        return JSONResponse({'detail': 'Device not found'}, status_code=404)
    
    elif request.method == 'PUT':
        data = await request.json()
        success = manager.update_device(device_id, data)
        # If EEP changed, re-publish discovery logic needs to trigger in main service
        # For now we assume restart/reload or next telegram fixes it
        if success: return JSONResponse({'status': 'updated'})
        return JSONResponse({'detail': 'Update failed'}, status_code=400)
    
    elif request.method == 'DELETE':
        mqtt = service_state.get_mqtt_handler()
        device = manager.get_device(device_id)
        if mqtt and device:
            loader = service_state.get_eep_loader()
            profile = loader.get_profile(device['eep']) if loader else None
            entities = profile.get_entities() if profile else []
            mqtt.remove_device(device_id, entities)

        success = manager.remove_device(device_id)
        if success: return JSONResponse({'status': 'deleted'})
        return JSONResponse({'detail': 'Delete failed'}, status_code=400)

async def api_eep_profiles(request):
    loader = service_state.get_eep_loader()
    if not loader: return JSONResponse({'profiles': []})
    return JSONResponse({'profiles': loader.list_profiles()})

# Routes
routes = [
    Route('/', endpoint=homepage),
    Route('/api/status', endpoint=api_status),
    Route('/api/system/discovery', endpoint=api_discovery_control, methods=['POST']),
    Route('/api/devices', endpoint=api_devices, methods=['GET', 'POST']),
    Route('/api/devices/{device_id}', endpoint=api_device_detail, methods=['GET', 'PUT', 'DELETE']),
    Route('/api/eep-profiles', endpoint=api_eep_profiles),
]

middleware = [Middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])]
app = Starlette(debug=True, routes=routes, middleware=middleware)
