from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from .tools.image_tools import CharacterImageGeneratorTool
from typing import List
# If you want to run a snippet of code before or after the crew starts,
# you can use the @before_kickoff and @after_kickoff decorators
# https://docs.crewai.com/concepts/crews#example-crew-class-with-decorators

@CrewBase
class Cluedogenai():
    """Cluedogenai crew"""

    agents: List[BaseAgent]

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
    # If you would like to add tools to your agents, you can learn more about it here:
    # https://docs.crewai.com/concepts/agents#agent-tools
    @agent
    def narrative_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['narrative_agent'], # type: ignore[index]
            verbose=True
        )

    @agent
    def character_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['character_agent'], # type: ignore[index]
            verbose=True
        )
    
    @agent
    def dialogue_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['dialogue_agent'], # type: ignore[index]
            verbose=True
        )
    
    @agent
    def vision_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['vision_agent'],  # type: ignore[index]
            tools=[CharacterImageGeneratorTool()],
            verbose=True,
            allow_delegation=False,  # probar a cambiar a True si quieres que delegue
        )

    # To learn more about structured task outputs,
    # task dependencies, and task callbacks, check out the documentation:
    # https://docs.crewai.com/concepts/tasks#overview-of-a-task
    @task
    def create_scene_blueprint(self) -> Task:
        return Task(
            config=self.tasks_config['create_scene_blueprint'], # type: ignore[index]
        )

    @task
    def define_characters(self) -> Task:
        return Task(
            config=self.tasks_config['define_characters'], # type: ignore[index]
        )
    
    @task
    def generate_suspect_dialogue(self) -> Task:
        return Task(
            config=self.tasks_config['generate_suspect_dialogue'], # type: ignore[index]
        )
    
    @task
    def design_scene_visuals(self) -> Task:
        return Task(
            config=self.tasks_config['design_scene_visuals'], # type: ignore[index]
        )

    @crew
    def setup_crew(self) -> Crew:
        """Crew solo para generar la escena inicial y los sospechosos."""
        return Crew(
            agents=[
                self.narrative_agent(),
                self.character_agent(),
                self.vision_agent(),
            ],
            tasks=[
                self.create_scene_blueprint(),
                self.define_characters(),
                self.design_scene_visuals(),
            ],
            process=Process.sequential,
            verbose=True,
        )
    

    @crew
    def dialogue_crew(self) -> Crew:
        """Crew rápido: solo genera la respuesta del sospechoso."""
        return Crew(
            agents=[
                self.dialogue_agent(),
            ],
            tasks=[
                self.generate_suspect_dialogue(),
            ],
            process=Process.sequential,
            verbose=False,  # menos ruido en consola
        )


    # Si quieres, puedes dejar la crew “grande” tal cual para tests manuales:
    @crew
    def full_crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
