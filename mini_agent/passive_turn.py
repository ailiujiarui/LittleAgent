from mini_agent.models import InboundMessage


class PassiveTurnPipeline:
    async def run(self, message: InboundMessage):
        raise NotImplementedError("passive turn pipeline is not configured")
