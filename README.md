# Film Recommendation App

An AI-powered film recommendation platform built around a user's Letterboxd history.

Users can import their viewing data through either manual Letterboxd CSV upload or Letterboxd RSS sync. The system builds a personalized taste profile, generates weekly and all-time viewing insights, and powers a chat-based recommender that suggests films based on both user taste and a broader movie corpus.

## Features

- AI film recommendation chat interface
- Letterboxd manual CSV import
- Letterboxd RSS sync for recurring updates
- Personalized taste profile generation
- Film Bank to store recommended films
- User feedback on recommendations
- Weekly stats report
- All-time stats report
- TMDB enrichment for metadata such as posters, overviews, cast, directors, keywords, and more

## Tech Stack

### Frontend
- React
- React Router
- Custom chat interface
- Local storage chat persistence

### Backend
- Django
- Django REST Framework
- SimpleJWT authentication
- PostgreSQL
- OpenAI Responses API + file search / vector stores
- TMDB integration

## Core Product Flow

1. A user signs up and authenticates.
2. The user imports Letterboxd data through:
   - manual CSV upload
   - or RSS sync
3. Imported watch history is normalized into:
   - `MovieUser`
   - `WatchEvent`
4. Movies missing metadata are queued for TMDB enrichment.
5. A user taste profile is built and indexed into a vector store.
6. The user chats with the recommender.
7. Recommendations are filtered against already watched and already recommended films.
8. Recommended films are stored in the Film Bank.
9. Feedback from the Film Bank can later influence future taste updates.

## Main Features in Detail

### 1. Chat Recommender
The chat recommender uses OpenAI with retrieval over:
- a global movie corpus
- an optional user taste vector store

The backend validates recommendation candidates against the local movie database before returning them to the frontend.

### 2. Letterboxd Imports
Users can bring in their Letterboxd history in two ways:

#### Manual CSV Import
Supports:
- watched
- reviews
- watchlist
- likes / films

#### RSS Sync
Users can link their Letterboxd username or profile URL. The app builds the RSS URL automatically and syncs recent public activity.

### 3. Film Bank
The Film Bank stores recommended movies for the user and allows:
- viewing previously recommended films
- dismissing a recommendation
- rating recommendation quality
- marking whether the user watched it
- adding optional written feedback

### 4. Stats
The app generates:
- weekly stats
- all-time stats

These use normalized watch data and include:
- recent watches
- top genres
- top actors
- top directors
- watch counts
- decade breakdowns
- total runtime watched

## Data Model Overview

### Key models
- `User`
- `Movie`
- `MovieUser`
- `WatchEvent`
- `FilmBank`
- `ImportBatch`
- `Genre`
- `Person`
- `MovieGenre`
- `MovieCast`
- `MovieCrew`

### Important model responsibilities

#### `Movie`
Stores the central movie corpus and enriched metadata.

#### `MovieUser`
Stores user-specific state for a movie:
- rating
- review
- watch status
- watchlist state
- liked state
- watched date
- rewatch flag

#### `WatchEvent`
Stores normalized watch events, especially useful for stats and repeated watch logging.

#### `FilmBank`
Stores recommendations shown to a user, plus user feedback.

## Project Structure

```bash
server/
  api/
    management/
    services/
    tasks/
    views/
    serializer.py
    models.py

client/
  src/
    components/
    pages/
    api/
    context/
