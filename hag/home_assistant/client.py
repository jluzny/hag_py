"""
Home Assistant WebSocket and REST client.

"""

import asyncio
import json
import aiohttp
from typing import Dict, Any, Optional, Callable, List
from urllib.parse import urljoin
import structlog

from ..config.settings import HassOptions
from .models import HassEvent, HassState, HassServiceCall, WebSocketMessage

logger = structlog.get_logger(__name__)

class HomeAssistantClient:
    """
    Home Assistant client with WebSocket and REST API support.
    
    
    """

    def __init__(self, config: HassOptions):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.message_id = 1
        self.connected = False
        self.running = False
        self._reconnect_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect to Home Assistant WebSocket API."""
        if self.connected:
            logger.warning("Already connected to Home Assistant")
            return

        logger.info("Connecting to Home Assistant", 
                   ws_url=self.config.ws_url,
                   rest_url=self.config.rest_url)

        # Create HTTP session
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Authorization": f"Bearer {self.config.token}"}
        )

        # Connect with retry logic
        for attempt in range(self.config.max_retries):
            try:
                await self._connect_websocket()
                self.connected = True
                self.running = True
                
                # Start message handling loop
                asyncio.create_task(self._message_loop())
                
                logger.info("Connected to Home Assistant successfully")
                return
                
            except Exception as e:
                logger.warning("Connection attempt failed",
                             attempt=attempt + 1,
                             max_retries=self.config.max_retries,
                             error=str(e))
                
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay_ms / 1000.0)
                else:
                    logger.error("Failed to connect after all retries")
                    raise ConnectionError(f"Failed to connect to Home Assistant: {e}")

    async def _connect_websocket(self) -> None:
        """Establish WebSocket connection and authenticate."""
        self.ws = await self.session.ws_connect(self.config.ws_url)
        
        # Read auth_required message
        auth_msg = await self.ws.receive_json()
        if auth_msg.get("type") != "auth_required":
            raise ConnectionError(f"Unexpected auth message: {auth_msg}")
        
        # Send auth message
        auth_request = {
            "type": "auth",
            "access_token": self.config.token
        }
        await self.ws.send_str(json.dumps(auth_request))
        
        # Read auth response
        auth_response = await self.ws.receive_json()
        if auth_response.get("type") != "auth_ok":
            raise ConnectionError(f"Authentication failed: {auth_response}")
        
        logger.debug("WebSocket authentication successful")

    async def disconnect(self) -> None:
        """Disconnect from Home Assistant."""
        logger.info("Disconnecting from Home Assistant")
        
        self.running = False
        self.connected = False
        
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        if self.session and not self.session.closed:
            await self.session.close()

    async def get_state(self, entity_id: str) -> HassState:
        """
        Get entity state via REST API.
        
        
        """
        if not self.session:
            raise ConnectionError("Not connected to Home Assistant")
        
        url = urljoin(self.config.rest_url, f"/api/states/{entity_id}")
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return HassState.from_dict(data)
                elif response.status == 404:
                    raise ValueError(f"Entity not found: {entity_id}")
                else:
                    error_text = await response.text()
                    raise ConnectionError(f"Failed to get state for {entity_id}: {response.status} - {error_text}")
                    
        except aiohttp.ClientError as e:
            logger.error("HTTP client error getting state", 
                        entity_id=entity_id, 
                        error=str(e))
            raise ConnectionError(f"Client error getting state for {entity_id}: {e}")

    async def call_service(self, service_call: HassServiceCall) -> Dict[str, Any]:
        """
        Call Home Assistant service via WebSocket.
        
        
        """
        if not self.ws or self.ws.closed:
            raise ConnectionError("WebSocket not connected")

        message = {
            "id": self.message_id,
            "type": "call_service",
            **service_call.to_dict()
        }
        
        self.message_id += 1
        
        logger.debug("Calling service",
                    domain=service_call.domain,
                    service=service_call.service,
                    message_id=message["id"])
        
        try:
            await self.ws.send_str(json.dumps(message))
            
            # Wait for response (simplified - real implementation would track message IDs)
            # For now, assume success if no immediate error
            return {"success": True}
            
        except Exception as e:
            logger.error("Failed to call service",
                        domain=service_call.domain,
                        service=service_call.service,
                        error=str(e))
            raise

    async def subscribe_events(self, event_type: Optional[str] = None) -> None:
        """Subscribe to Home Assistant events."""
        if not self.ws or self.ws.closed:
            raise ConnectionError("WebSocket not connected")

        message = {
            "id": self.message_id,
            "type": "subscribe_events"
        }
        
        if event_type:
            message["event_type"] = event_type
        
        self.message_id += 1
        
        logger.debug("Subscribing to events", event_type=event_type or "all")
        await self.ws.send_str(json.dumps(message))

    def add_event_handler(self, event_type: str, handler: Callable[[HassEvent], None]) -> None:
        """Add event handler for specific event type."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        
        self.event_handlers[event_type].append(handler)
        logger.debug("Added event handler", event_type=event_type)

    async def _message_loop(self) -> None:
        """
        Main message handling loop.
        
        
        """
        logger.info("Starting WebSocket message loop")
        
        try:
            while self.running and self.ws and not self.ws.closed:
                try:
                    message = await self.ws.receive()
                    
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(json.loads(message.data))
                    elif message.type == aiohttp.WSMsgType.ERROR:
                        logger.error("WebSocket error", error=self.ws.exception())
                        break
                    elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING):
                        logger.info("WebSocket closed by server")
                        break
                        
                except asyncio.CancelledError:
                    logger.info("Message loop cancelled")
                    break
                except Exception as e:
                    logger.error("Error in message loop", error=str(e))
                    break
                    
        finally:
            if self.running:
                # Connection lost, attempt reconnection
                logger.warning("WebSocket connection lost, attempting reconnection")
                self.connected = False
                self._reconnect_task = asyncio.create_task(self._reconnect())

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        try:
            message = WebSocketMessage.from_dict(data)
            
            # Debug: Log all messages to see what we're receiving
            logger.debug("Received WebSocket message", 
                        message_type=message.message_type,
                        has_event=message.event is not None,
                        event_type=message.event.event_type if message.event else None)
            
            if message.event and message.event.event_type in self.event_handlers:
                logger.debug("Processing event", 
                           event_type=message.event.event_type,
                           handlers_count=len(self.event_handlers[message.event.event_type]))
                
                # Dispatch to registered handlers
                for handler in self.event_handlers[message.event.event_type]:
                    try:
                        await handler(message.event)
                    except Exception as e:
                        logger.error("Error in event handler",
                                   event_type=message.event.event_type,
                                   error=str(e))
            elif message.event:
                logger.debug("Received unhandled event", 
                           event_type=message.event.event_type,
                           available_handlers=list(self.event_handlers.keys()))
            
        except Exception as e:
            logger.error("Failed to handle WebSocket message", 
                        data=data, 
                        error=str(e))

    async def _reconnect(self) -> None:
        """Reconnect to Home Assistant with exponential backoff."""
        backoff_delay = 1.0
        max_delay = 60.0
        
        while self.running and not self.connected:
            try:
                logger.info("Attempting to reconnect to Home Assistant")
                await self._connect_websocket()
                
                self.connected = True
                asyncio.create_task(self._message_loop())
                
                logger.info("Reconnected to Home Assistant successfully")
                return
                
            except Exception as e:
                logger.warning("Reconnection attempt failed", 
                             delay=backoff_delay,
                             error=str(e))
                
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * 2, max_delay)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()