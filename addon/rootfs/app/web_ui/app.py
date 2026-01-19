"""
Web UI Application (Starlette)
Handles HTTP requests and serves the dashboard
"""
import os
import json
import logging
from starlette.applications import Starlette
from starlette.responses import JSONResponse, HTMLResponse, Response
from starlette.routing import Route, Mount
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from service_state import service_state

logger = logging.getLogger(__name__)

# Paths
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_PATH = os.path.join(BASE_PATH, 'templates')

async def homepage(request):
    """Serve the main dashboard with dynamic version injection"""
    try:
        with open(os.path.join(TEMPLATES_PATH, 'dashboard_full.html'), 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Inject Version from Environment (set by run.sh)
        version = os.getenv('ADDON_VERSION', 'dev')
        content = content.replace('{{VERSION}}', version)
        
        return HTMLResponse(content)
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        return HTMLResponse(f"Error loading dashboard: {e}", status_code=500)

# --- API Endpoints ---

async def api_status(request):
    """Get service status"""
    return JSONResponse(service_state.get_status())

async def api_gateway_info(request):
    """Get gateway info"""
    return JSONResponse(service_state.get_gateway_info())

async def api_devices(request):
    """List all devices"""
    if request.method == 'GET':
        manager = service_state.get_device_manager()
        if not manager:
            return JSONResponse({'error': 'Service not ready'}, status_code=503)
        return JSONResponse({'devices': manager.list_devices()})
    
    elif request.method == 'POST':
        # Add new device
        try:
            data = await request.json()
            manager = service_state.get_device_manager()
            if not manager:
                return JSONResponse({'error': 'Service not ready'}, status_code=503)
            
            success = manager.add_device(
                data.get('id'),
                data.get('name'),
                data.get('eep'),
                data.get('manufacturer', 'EnOcean')
            )
            
            if success:
                # Trigger discovery update via MQTT
                mqtt = service_state.get_mqtt_handler()
                device = manager.get_device(data.get('id'))
                if mqtt and device:
                    # Async task in background ideally, but ok for now
                    # We need to access the main service loop to publish properly if async
                    # For now, we rely on the restart/reload or immediate effect if implemented
                    pass
                return JSONResponse({'status': 'created'})
            else:
                return JSONResponse({'detail': 'Device ID already exists or invalid EEP'}, status_code=400)
        except Exception as e:
            return JSONResponse({'detail': str(e)}, status_code=400)

async def api_device_detail(request):
    """Get/Update/Delete single device"""
    device_id = request.path_params['device_id']
    manager = service_state.get_device_manager()
    if not manager:
        return JSONResponse({'error': 'Service not ready'}, status_code=503)
    
    if request.method == 'GET':
        device = manager.get_device(device_id)
        if device:
            return JSONResponse(device)
        return JSONResponse({'detail': 'Device not found'}, status_code=404)
    
    elif request.method == 'PUT':
        data = await request.json()
        success = manager.update_device(device_id, data)
        if success:
            return JSONResponse({'status': 'updated'})
        return JSONResponse({'detail': 'Update failed'}, status_code=400)
    
    elif request.method == 'DELETE':
        # Remove from MQTT first
        mqtt = service_state.get_mqtt_handler()
        device = manager.get_device(device_id)
        
        # We need EEP info to know which entities to remove
        if mqtt and device:
            eep_loader = service_state.get_eep_loader()
            if eep_loader:
                profile = eep_loader.get_profile(device['eep'])
                if profile:
                    mqtt.remove_device(device_id, profile.get_entities())

        success = manager.remove_device(device_id)
        if success:
            return JSONResponse({'status': 'deleted'})
        return JSONResponse({'detail': 'Delete failed'}, status_code=400)

async def api_device_action(request):
    """Enable/Disable device"""
    device_id = request.path_params['device_id']
    action = request.path_params['action']
    
    manager = service_state.get_device_manager()
    if not manager:
        return JSONResponse({'error': 'Service not ready'}, status_code=503)
    
    device = manager.get_device(device_id)
    if not device:
        return JSONResponse({'detail': 'Device not found'}, status_code=404)
    
    updates = {'enabled': (action == 'enable')}
    manager.update_device(device_id, updates)
    return JSONResponse({'status': 'updated'})

async def api_eep_profiles(request):
    """List all EEP profiles"""
    loader = service_state.get_eep_loader()
    if not loader:
        return JSONResponse({'profiles': []})
    
    return JSONResponse({'profiles': loader.list_profiles()})

async def api_eep_detail(request):
    """Get EEP profile details"""
    eep_code = request.path_params['eep_code']
    loader = service_state.get_eep_loader()
    if not loader:
        return JSONResponse({'error': 'Service not ready'}, status_code=503)
    
    profile = loader.get_profile(eep_code)
    if profile:
        return JSONResponse(profile.to_dict())
    return JSONResponse({'detail': 'Profile not found'}, status_code=404)

async def api_suggest_profiles(request):
    """Get suggested profiles for a device ID based on cached teach-in telegrams"""
    device_id = request.path_params['device_id']
    
    # Get cached EEPs from teach-in detection
    detected_eeps = service_state.get_detected_profiles(device_id)
    loader = service_state.get_eep_loader()
    
    suggestions = []
    if loader and detected_eeps:
        for eep in detected_eeps:
            profile = loader.get_profile(eep)
            if profile:
                suggestions.append({
                    'eep': profile.eep,
                    'title': profile.title,
                    'description': profile.description
                })
    
    return JSONResponse({
        'device_id': device_id,
        'has_suggestions': len(suggestions) > 0,
        'suggested_profiles': suggestions
    })

# Routes definition
routes = [
    Route('/', endpoint=homepage),
    Route('/api/status', endpoint=api_status),
    Route('/api/gateway-info', endpoint=api_gateway_info),
    Route('/api/devices', endpoint=api_devices, methods=['GET', 'POST']),
    Route('/api/devices/{device_id}', endpoint=api_device_detail, methods=['GET', 'PUT', 'DELETE']),
    Route('/api/devices/{device_id}/{action}', endpoint=api_device_action, methods=['POST']),
    Route('/api/eep-profiles', endpoint=api_eep_profiles),
    Route('/api/eep-profiles/{eep_code}', endpoint=api_eep_detail),
    Route('/api/suggest-profiles/{device_id}', endpoint=api_suggest_profiles),
]

# CORS middleware for development flexibility
middleware = [
    Middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
]

# Create app
app = Starlette(debug=True, routes=routes, middleware=middleware)
