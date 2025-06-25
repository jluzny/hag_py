"""
LangChain HVAC Agent for intelligent climate control.

AI-enhanced HVAC coordinator with LangChain integration.
"""

from typing import Dict, Any, List, Callable
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import Tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import structlog

from ..home_assistant.client import HomeAssistantClient
from ..config.settings import HvacOptions
from .state_machine import HVACStateMachine
from .tools import TemperatureMonitorTool, HVACControlTool, SensorReaderTool

logger = structlog.get_logger(__name__)

class HVACAgent:
    """
    Intelligent HVAC control agent using LangChain.

    
    """

    def __init__(
        self,
        ha_client: HomeAssistantClient,
        hvac_options: HvacOptions,
        state_machine: HVACStateMachine,
        llm_model: str = "gpt-3.5-turbo",
        temperature: float = 0.1,
    ):
        self.ha_client = ha_client
        self.hvac_options = hvac_options
        self.state_machine = state_machine

        # Initialize LLM with conservative temperature for HVAC decisions
        self.llm = ChatOpenAI(
            model=llm_model,
            temperature=temperature,  # Conservative for safety
            max_tokens=1000,  # type: ignore[call-arg]
        )

        # Initialize tools
        self.tools = self._create_tools()

        # Create agent
        self.agent = self._create_agent()

        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {}

        logger.info(
            "HVAC Agent initialized",
            model=llm_model,
            tools_count=len(self.tools),
            temp_sensor=hvac_options.temp_sensor,
            system_mode=hvac_options.system_mode,
        )

    def _create_tools(self) -> List[Tool]:
        """Create LangChain tools for HVAC operations."""

        # Core HVAC tools
        temp_monitor = TemperatureMonitorTool(self.ha_client, self.state_machine)
        hvac_control = HVACControlTool(
            self.ha_client, self.hvac_options, self.state_machine
        )
        sensor_reader = SensorReaderTool(self.ha_client)

        # Convert to LangChain tools
        tools = [
            Tool.from_function(
                func=temp_monitor._arun,
                name=temp_monitor.name,
                description=temp_monitor.description,
                coroutine=temp_monitor._arun,
            ),
            Tool.from_function(
                func=hvac_control._arun,
                name=hvac_control.name,
                description=hvac_control.description,
                coroutine=hvac_control._arun,
            ),
            Tool.from_function(
                func=sensor_reader._arun,
                name=sensor_reader.name,
                description=sensor_reader.description,
                coroutine=sensor_reader._arun,
            ),
        ]

        return tools

    def _create_agent(self) -> AgentExecutor:
        """Create the LangChain agent with HVAC-specific prompt."""

        system_prompt = self._get_system_prompt()

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        # Create agent
        agent = create_openai_tools_agent(self.llm, self.tools, prompt)

        # Create executor with error handling
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=10,
            early_stopping_method="generate",
            handle_parsing_errors=True,
        )

        return agent_executor

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the HVAC agent."""

        return f"""You are an intelligent HVAC control agent for a Home Assistant system. Your primary goal is to maintain comfortable indoor temperatures while optimizing energy efficiency and equipment longevity.

SYSTEM CONFIGURATION:
- Indoor Temperature Sensor: {self.hvac_options.temp_sensor}
- Outdoor Temperature Sensor: {self.hvac_options.outdoor_sensor}
- System Mode: {self.hvac_options.system_mode.value}
- Heating Target: {self.hvac_options.heating.temperature}°C
- Cooling Target: {self.hvac_options.cooling.temperature}°C

OPERATIONAL THRESHOLDS:
Heating:
- Indoor Range: {self.hvac_options.heating.temperature_thresholds.indoor_min}°C - {self.hvac_options.heating.temperature_thresholds.indoor_max}°C
- Outdoor Range: {self.hvac_options.heating.temperature_thresholds.outdoor_min}°C - {self.hvac_options.heating.temperature_thresholds.outdoor_max}°C

Cooling:
- Indoor Range: {self.hvac_options.cooling.temperature_thresholds.indoor_min}°C - {self.hvac_options.cooling.temperature_thresholds.indoor_max}°C  
- Outdoor Range: {self.hvac_options.cooling.temperature_thresholds.outdoor_min}°C - {self.hvac_options.cooling.temperature_thresholds.outdoor_max}°C

CONTROLLED ENTITIES:
{chr(10).join([f"- {entity.entity_id} (enabled: {entity.enabled}, defrost: {entity.defrost})" for entity in self.hvac_options.hvac_entities])}

DECISION PRINCIPLES:
1. **Safety First**: Never operate outside configured thresholds
2. **Comfort Priority**: Maintain indoor temperatures within comfort ranges
3. **Energy Efficiency**: Minimize unnecessary heating/cooling cycles
4. **Equipment Protection**: Avoid rapid mode switches and extreme settings
5. **User Preference**: Respect manual overrides and system mode settings

AVAILABLE TOOLS:
- temperature_monitor: Get current indoor/outdoor temperatures and update system state
- hvac_control: Control HVAC entities (heat/cool/off/auto_evaluate)
- sensor_reader: Read any Home Assistant sensor data

RESPONSE GUIDELINES:
- Always check current conditions before making decisions
- Explain your reasoning for HVAC actions
- Consider energy efficiency and comfort balance
- Report any validation issues or recommendations
- Be conservative with temperature changes
- Monitor system state after actions

TYPICAL WORKFLOW:
1. Monitor temperatures using temperature_monitor tool
2. Analyze conditions against thresholds and comfort requirements
3. Use hvac_control with appropriate action (heat/cool/off/auto_evaluate)
4. Provide clear explanation of actions taken and reasoning

Remember: You are controlling real HVAC equipment that affects user comfort and energy costs. Be thoughtful and conservative in your decisions."""

    async def process_temperature_change(
        self, event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process temperature sensor change event.

        Enhanced version of Rust state change processing with AI analysis.
        """

        logger.info(
            "Processing temperature change event", entity_id=event_data.get("entity_id")
        )

        try:
            # Prepare AI prompt for temperature evaluation
            prompt = f"""
            A temperature sensor has reported a new value. Please analyze the current HVAC situation and take appropriate action.
            
            Event Details:
            - Entity: {event_data.get("entity_id", "unknown")}
            - New State: {event_data.get("new_state", "unknown")}
            - Old State: {event_data.get("old_state", "unknown")}
            
            Please:
            1. Use the temperature_monitor tool to get comprehensive current conditions
            2. Analyze if any HVAC action is needed based on:
               - Current indoor vs target temperatures
               - Outdoor conditions vs operational thresholds
               - Current system state and mode
               - Energy efficiency considerations
            3. If action is needed, use hvac_control tool to implement changes
            4. Provide a summary of your analysis and actions taken
            
            Focus on maintaining comfort while being energy efficient.
            """

            # Execute AI agent
            response = await self.agent.ainvoke({"input": prompt})

            result = {
                "success": True,
                "agent_response": response.get("output", ""),
                "event_processed": event_data.get("entity_id"),
                "timestamp": self._get_timestamp(),
            }

            logger.info(
                "Temperature change processed by AI agent",
                entity_id=event_data.get("entity_id"),
                response_length=len(response.get("output", "")),
            )

            return result

        except Exception as e:
            logger.error(
                "Failed to process temperature change",
                event_data=event_data,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "event_data": event_data,
                "timestamp": self._get_timestamp(),
            }

    async def manual_override(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        Handle manual HVAC override requests.

        Allows manual control while still leveraging AI validation and optimization.
        """

        logger.info("Processing manual override", action=action, kwargs=kwargs)

        try:
            prompt = f"""
            A manual HVAC override has been requested. Please validate and execute this request.
            
            Requested Action: {action}
            Additional Parameters: {kwargs}
            
            Please:
            1. Use temperature_monitor to check current conditions
            2. Validate if the requested action is safe and appropriate
            3. If valid, use hvac_control to execute the action
            4. If not valid, explain why and suggest alternatives
            5. Provide feedback on the action taken
            
            Remember: This is a manual override, so be more permissive than normal automatic operation,
            but still ensure safety and provide warnings if the action seems inefficient.
            """

            response = await self.agent.ainvoke({"input": prompt})

            return {
                "success": True,
                "agent_response": response.get("output", ""),
                "requested_action": action,
                "parameters": kwargs,
                "timestamp": self._get_timestamp(),
            }

        except Exception as e:
            logger.error("Manual override failed", action=action, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "requested_action": action,
                "timestamp": self._get_timestamp(),
            }

    async def evaluate_efficiency(self) -> Dict[str, Any]:
        """
        Perform an AI-powered efficiency analysis of the HVAC system.
        """

        logger.info("Starting HVAC efficiency evaluation")

        prompt = """
        Please perform a comprehensive HVAC efficiency analysis.
        
        Steps:
        1. Use temperature_monitor to get current system status and conditions
        2. Use sensor_reader to check additional relevant sensors if available
        3. Analyze the current operation for efficiency opportunities:
           - Are we maintaining appropriate temperature differentials?
           - Is the system cycling appropriately?
           - Are we operating within optimal outdoor condition ranges?
           - Any energy waste or comfort issues?
        4. Provide recommendations for optimization
        5. If immediate improvements are possible, suggest or implement them
        
        Focus on both energy efficiency and comfort optimization.
        """

        try:
            response = await self.agent.ainvoke({"input": prompt})

            return {
                "success": True,
                "analysis": response.get("output", ""),
                "timestamp": self._get_timestamp(),
            }

        except Exception as e:
            logger.error("Efficiency evaluation failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "timestamp": self._get_timestamp(),
            }

    async def get_status_summary(self) -> Dict[str, Any]:
        """Get comprehensive system status with AI insights."""

        prompt = """
        Please provide a comprehensive HVAC system status summary.
        
        Include:
        1. Current temperatures (indoor/outdoor) using temperature_monitor
        2. Current system state and operation mode
        3. Recent actions or changes
        4. Comfort analysis (too hot/cold/comfortable)
        5. Efficiency assessment
        6. Any alerts or recommendations
        
        Provide a clear, concise summary suitable for users.
        """

        try:
            response = await self.agent.ainvoke({"input": prompt})

            # Also get machine-readable status
            machine_status = self.state_machine.get_status()

            return {
                "success": True,
                "ai_summary": response.get("output", ""),
                "machine_status": machine_status,
                "timestamp": self._get_timestamp(),
            }

        except Exception as e:
            logger.error("Status summary failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "machine_status": self.state_machine.get_status(),
                "timestamp": self._get_timestamp(),
            }

    def add_event_handler(self, event_type: str, handler: Callable) -> None:
        """Add event handler for specific events."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []

        self.event_handlers[event_type].append(handler)
        logger.debug("Added event handler", event_type=event_type)

    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle incoming events and dispatch to handlers."""

        # Process temperature sensor changes
        if (
            event_type == "state_changed"
            and event_data.get("entity_id") == self.hvac_options.temp_sensor
        ):
            await self.process_temperature_change(event_data)

        # Dispatch to registered handlers
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    await handler(event_data)
                except Exception as e:
                    logger.error(
                        "Event handler failed", event_type=event_type, error=str(e)
                    )

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime

        return datetime.now().isoformat()

