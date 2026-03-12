# Drift System Architecture

DriftSystem v0.1 is a semantic scene generation engine for Minecraft. The system converts player intent into structured world patches that can be applied by the plugin layer.

## End-to-End Flow

1. Player Input: raw commands, chat text, or interaction signals.
2. Semantic Engine: parses intent and extracts structured goals.
3. Scene Prediction: predicts candidate scene patterns.
4. Theme Resolver: aligns scene candidates with active theme rules.
5. Fragment Selection: selects reusable narrative and gameplay fragments.
6. Scene Assembler: composes final scene artifacts.
7. World Patch: generates deterministic world patch operations.
8. Minecraft Plugin: applies patches and syncs runtime state in server world.

## Core Modules

- semantic_engine: intent parsing and semantic normalization.
- scene_library: scene templates and retrieval strategy.
- fragment_loader: fragment indexing and loading pipeline.
- scene_assembler: multi-fragment composition into executable scenes.
- world_patch_generator: conversion from scene graph to patch instructions.
- minecraft_plugin_bridge: protocol boundary between backend output and in-game execution.

## Design Principles

- Deterministic generation where possible for reproducibility.
- Clear separation between semantic reasoning and runtime application.
- Modular scene composition to keep content extensible.
- Plugin-bridge compatibility as a first-class constraint.
