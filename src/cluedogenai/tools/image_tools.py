# -*- coding: utf-8 -*-
"""
Imagen generator tool for suspects, using Google Generative AI (Imagen 3).
"""

import os
import json
from io import BytesIO
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, ConfigDict

# Gemini / Imagen 3
from google import genai
from google.genai import types

# Para guardar la imagen
from PIL import Image


class CharacterImageGenInput(BaseModel):
    model_config = ConfigDict(extra="allow")  # ✅ deja pasar campos extra (id, name, etc.)
    character_data: str | None = Field(
        default=None,
        description="Un string JSON válido que representa a UN SOLO sospechoso."
    )


class CharacterImageGeneratorTool(BaseTool):
    name: str = "Generate Character Image"
    description: str = "Genera un archivo de imagen .png para un personaje y devuelve la ruta."
    args_schema: Type[BaseModel] = CharacterImageGenInput

    def _run(self, character_data: str | None = None, **kwargs) -> str:
        # ✅ Si el agente NO mandó character_data y mandó el sospechoso como dict en kwargs:
        if character_data is None:
            if kwargs:
                character_data = json.dumps(kwargs, ensure_ascii=False)
            else:
                return "Error: No se recibió character_data ni campos del personaje."

        # ✅ Si igual llega como dict/list por algún motivo, convertirlo a str JSON
        if isinstance(character_data, (dict, list)):
            character_data = json.dumps(character_data, ensure_ascii=False)
        # 1. API key de Gemini / Imagen 3
        api_key = os.getenv("GEMINI_API_KEY")  # O el nombre que uses en tu entorno
        if not api_key:
            return "Error: GEMINI_API_KEY no encontrado en las variables de entorno."

        # 2. Inicializar cliente de Google Generative AI
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            return f"Error inicializando cliente de Gemini: {e}"

        # 3. Carpeta donde guardamos las imágenes
        base_path = os.getcwd()
        output_dir = os.path.join(base_path, "src", "cluedogenai", "generated_images")
        os.makedirs(output_dir, exist_ok=True)

        # 4. Parsear el JSON del sospechoso
        try:
            if isinstance(character_data, str):
                cleaned = character_data.replace("```json", "").replace("```", "").strip()
                suspect = json.loads(cleaned)
            else:
                suspect = character_data
        except Exception as e:
            return f"Error parseando character_data como JSON: {e}"

        # 5. Extraer atributos del sospechoso
        name = suspect.get("name", "Unknown")
        role = suspect.get("role", "person")
        age = suspect.get("age", "adult")
        personality = suspect.get("personality", "neutral")

        physical = suspect.get("physical_description", {})
        build = physical.get("build", "average build")
        face = physical.get("face", "distinctive face")
        hair = physical.get("hair", "styled hair")
        clothes = physical.get("upper_clothing", "casual clothes")
        features = physical.get("distinctive_features", "")
        clue_object = suspect.get("clue_object", "")

        ESTILO_MISTERIO = (
            "Atmosphere: Tense murder mystery vibe, Agatha Christie aesthetic, suspicious mood. "
            "Lighting: Dramatic chiaroscuro, volumetric fog, dramatic shadows but with visible background details. "
            "Camera: Shot on 35mm analog film, film grain, f/5.6 aperture, "
            "8k resolution, hyper-realistic, highly detailed skin texture. "
            "Composition: Cinematic film still."
        )

        # 6. Construimos el prompt maestro (igual que antes)
        prompt = (
            f"Low-angle dramatic shot of a {age} year old {role}. "
            f"Physical appearance: {build}, {hair}, {face}. "
            f"Wearing {clothes}. "
        )

        if features:
            prompt += f"Distinguishing feature: {features}. "

        if clue_object:
            prompt += (
                f"They are nervously holding or fidgeting with a {clue_object} in their hands. "
            )

        prompt += (
            f"Expression: {personality}, looking suspiciously at the camera. "
            "Location: A detailed, dimly lit room containing objects and atmosphere characteristic of their profession. "
            "The background is visible and rich in details related to their work environment. "
            f"{ESTILO_MISTERIO}"
        )

        print(f"🧠 Generando a {name} con Imagen 3 en {output_dir}...")

        # 7. Llamada a Imagen 3
        try:
            response = client.models.generate_images(
            model="imagen-4.0-fast-generate-001",  # ✅ modelo que sí tienes disponible
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
            ),
        )

            if not response.generated_images:
                return (
                    "Error generando la imagen: no se devolvieron imágenes "
                    "(posiblemente bloqueadas por filtros de seguridad)."
                )

            generated_image = response.generated_images[0]
            image_bytes = generated_image.image.image_bytes
            image = Image.open(BytesIO(image_bytes))

            # 8. Guardar archivo
            safe_name = str(name).replace(" ", "_")
            safe_role = str(role).replace(" ", "_")
            filename = f"{safe_name}_{safe_role}.png"
            full_path = os.path.join(output_dir, filename)

            image.save(full_path)

            rel_path = os.path.join("src", "cluedogenai", "generated_images", filename)
            return rel_path


        except Exception as e:
            return f"Error generando la imagen con Gemini/Imagen 3: {e}"
