# -*- coding: utf-8 -*-
"""
Created on Fri Dec 12 12:28:54 2025

@author: usuario
"""

import os
import json
from typing import Type
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from huggingface_hub import InferenceClient

class CharacterImageGenInput(BaseModel):
    character_data: str = Field(..., description="Un string JSON válido que representa a UN SOLO sospechoso.")

class CharacterImageGeneratorTool(BaseTool):
    name: str = "Generate Character Image"
    description: str = "Genera un archivo de imagen .png para un personaje y devuelve la ruta."
    args_schema: Type[BaseModel] = CharacterImageGenInput

    def _run(self, character_data: str) -> str:
        hf_token = os.getenv("HF_TOKEN") #MODIFICARLO SI CAMBIAMOS A GEMINI
        if not hf_token:
            return "Error: HF_TOKEN no encontrado."
        
        client = InferenceClient("black-forest-labs/FLUX.1-schnell", token=hf_token) #MODIFICARLO SI CAMBIAMOS A GEMINI

        # --- 1. CONFIGURACIÓN DE RUTAS (Aquí está el cambio) ---
        # Esto crea la carpeta dentro de 'src/cluedogenai/generated_images'
        # Asumiendo que ejecutas 'crewai run' desde la raíz del proyecto: en principio sí en app.py
        base_path = os.getcwd() # Obtiene la carpeta raíz del proyecto
        nombre_carpeta = os.path.join(base_path, "src", "cluedogenai", "generated_images")

        # Crear la carpeta si no existe
        if not os.path.exists(nombre_carpeta):
            os.makedirs(nombre_carpeta, exist_ok=True)
        # -------------------------------------------------------

        try:
            if isinstance(character_data, str):
                # Limpieza extra por si el LLM mete bloques de código markdown
                cleaned_data = character_data.replace("```json", "").replace("```", "").strip()
                datos_sospechoso = json.loads(cleaned_data)
            else:
                datos_sospechoso = character_data

            # Extracción de datos del JSON
            nombre = datos_sospechoso.get("name", "Unknown")
            rol = datos_sospechoso.get("role", "person")
            edad = datos_sospechoso.get("age", "adult")
            personalidad = datos_sospechoso.get("personality", "neutral")
            
            fisico = datos_sospechoso.get("physical_description", {})
            cuerpo = fisico.get("build", "average build")
            cara = fisico.get("face", "distinctive face")
            pelo = fisico.get("hair", "styled hair")
            ropa = fisico.get("upper_clothing", "casual clothes")
            rasgos = fisico.get("distinctive_features", "")
            objeto_pista= datos_sospechoso.get("clue_object", "")
            
            ESTILO_MISTERIO = (
                "Atmosphere: Tense murder mystery vibe, Agatha Christie aesthetic, suspicious mood. "
                "Lighting: Dramatic chiaroscuro, volumetric fog, Dramatic shadows but with visible background details. "
                "Camera: Shot on 35mm analog film, film grain, f/5.6 aperture, "
                "8k resolution, hyper-realistic, highly detailed skin texture. "
                "Composition: Cinematic film still."
            )

            prompt_maestro = (
                f"Low-angle dramatic shot of a {edad} year old {rol}. "
                f"Physical appearance: {cuerpo}, {pelo}, {cara}. "
                f"Wearing {ropa}. "
            )
            
            if rasgos:
                prompt_maestro += f"Distinguishing feature: {rasgos}. "
                
            if objeto_pista:
                # Lo ponemos como una acción sutil ("fidgeting with", "holding tightly")
                # para que no parezca un anuncio de producto, sino parte de la narrativa.
                prompt_maestro += f"They are nervously holding or fidgeting with a {objeto_pista} in their hands. "
                
            prompt_maestro += (
                f"Expression: {personalidad}, looking suspiciously at the camera. "
                "Location: A detailed, dimly lit room containing objects and atmosphere characteristic of a {rol}. "
                "The background is visible and rich in details related to their profession. "
                f"{ESTILO_MISTERIO}"
            )

            print(f"🧠 Generando a {nombre} en {nombre_carpeta}...")

            # Generación
            image = client.text_to_image(prompt_maestro, guidance_scale=0.0, num_inference_steps=4)
            
            # Nombre de archivo seguro
            safe_name = nombre.replace(' ', '_')
            safe_role = rol.replace(' ', '_')
            nombre_archivo = f"{safe_name}_{safe_role}.png"
            
            # Ruta completa final
            ruta_completa = os.path.join(nombre_carpeta, nombre_archivo)
            
            image.save(ruta_completa)
            
            # Devolvemos la ruta relativa para que el informe sea limpio
            ruta_relativa = os.path.join("src", "cluedogenai", "generated_images", nombre_archivo)
            return f"Imagen guardada en: {ruta_relativa}"

        except Exception as e:
            return f"Error generando la imagen: {str(e)}"