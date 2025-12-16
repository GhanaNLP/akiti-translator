---
title: English to Twi Translator
emoji: 🇬🇭
colorFrom: purple
colorTo: pink
sdk: gradio
sdk_version: 4.0.0
app_file: app.py
pinned: true
license: mit
---

# 🇬🇭 English to Twi Translator

A rule-based translator that converts English sentences to Twi (Akan language spoken in Ghana) using the urbans translation framework.

![Translator Screenshot](https://img.shields.io/badge/status-active-success) ![Python](https://img.shields.io/badge/python-3.8+-blue) ![Gradio](https://img.shields.io/badge/gradio-4.0+-orange)

## ✨ Features

- **Grammar-Based Translation**: Uses context-free grammar rules for accurate structure translation
- **Real urbans Framework**: Powered by the official urbans package from GitHub
- **Interactive Debug Mode**: Toggle to see the complete translation process
- **Smart Dictionary**: Word and phrase-based translation with proper noun support
- **Modern UI**: Beautiful, responsive interface with animations
- **Input Validation**: Ensures single sentences for accurate parsing
- **Example Sentences**: Quick-start with common translations

## 🚀 Quick Start

1. **Enter** an English sentence in the input box
2. **Click** "Translate to Twi" or press Enter
3. **View** the Twi translation
4. **Toggle** "Show detailed translation process" to see grammar parsing

## 📚 Examples

| English Sentence | Twi Translation |
|-----------------|-----------------|
| I love good dogs | Me dɔ papa kraman |
| how are you | ɛte sɛn |
| what is your name | wo dzin de sɛn |
| I am going to the market | Me kɔ edwamu |
| Kofi ne Kwame are going to Accra | Kofi ne Kwame kɔ Accra |

## 🛠️ Technical Architecture

### Components
1. **Frontend**: Gradio web interface
2. **Translation Engine**: urbans grammar-based framework
3. **Dictionary**: CSV-based word/phrase database
4. **Grammar Rules**: Custom CFG for English and transformation rules for Twi

### Dependencies
- `gradio`: Web interface framework
- `urbans`: Grammar-based translation engine (from GitHub)
- `nltk`: Natural language processing toolkit
- `urllib3`: HTTP client library

