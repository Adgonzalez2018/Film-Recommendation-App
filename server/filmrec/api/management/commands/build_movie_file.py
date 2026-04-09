#api/management/commands/build_movie_file.py
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Prefetch

from api.models import (
    Movie,
    MovieGenre,
    MovieCrew,
    MovieCast,
) # adjust import if needed

def build_movie_text(movie, genres, directors, cast_names):
    title = movie.title or "Unknown"
    year_str = f" ({movie.year})" if movie.year else ""

    parts = ["MOVIE", f"Title: {title}{year_str}"]

    if genres:
        parts.append(f"Genres: {', '.join(genres)}")
    if movie.tagline:
        parts.append(f"Tagline: {movie.tagline}")
    if directors:
        parts.append(f"Director: {', '.join(directors)}")
    if cast_names:
        parts.append(f"Cast: {', '.join(cast_names)}")
    if movie.keywords:
        parts.append(f"Keywords: {movie.keywords}")
    if movie.collection_name:
        parts.append(f"Series: {movie.collection_name}")
    if movie.overview:
        ov = movie.overview.strip()
        if len(ov) > 800:
            ov = ov[:800].rsplit(" ", 1)[0] + "..."
        parts.append(f"Overview: {ov}")

    return "\n".join(parts)

class Command(BaseCommand):
    help = "Build global movies JSONL for vector indexing."

    def add_arguments(self,parser):
        parser.add_argument("--out", type=str, default="movies_out")
        parser.add_argument("--filename", type=str, default="movies.jsonl")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--cast-n", type=int, default=5)

    def handle(self, *args, **opts):
        out_dir = Path(opts["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / opts["filename"]
        limit = opts["limit"]
        cast_n = opts["cast_n"]

        # prefetch related rows efficiently
        qs = (Movie.objects
              .filter(title__isnull=False)
              .exclude(title__exact="")
              .filter(tmdb_id__isnull=False)
              .order_by("id")
              .prefetch_related(
                Prefetch(
                    "moviegenre_set",
                    queryset=MovieGenre.objects.select_related("genre"),
                ),
                Prefetch(
                    "moviecrew_set",
                    queryset=MovieCrew.objects.select_related("person"),
                ),
                Prefetch(
                    "moviecast_set",
                    queryset=MovieCast.objects.select_related("person").order_by("order", "id"),
                ),
            )
        )
    
        if limit and limit > 0:
            qs = qs[:limit]

        count = 0
        with out_path.open("w", encoding="utf-8") as f:
            for m in qs:
                if not m.title:
                    continue

                has_signal = (
                    m.overview
                    or m.tmdb_id
                    or m.moviegenre_set.exists()
                    or m.moviecast_set.exists()
                    or m.moviecrew_set.exists()
                )

                if not has_signal:
                    continue

                genres = [mg.genre.name for mg in m.moviegenre_set.all() if mg.genre_id and mg.genre]
                directors = [
                    mc.person.name
                    for mc in m.moviecrew_set.all()
                    if mc.person_id and mc.person and (mc.job or "").strip().lower() == "director"
                ]

                cast = []
                for c in m.moviecast_set.all():
                    if c.person_id and c.person and c.person.name:
                        cast.append(c.person.name)
                    if len(cast) >= cast_n:
                        break

                text = build_movie_text(m, genres, directors, cast)

                doc = {
                    "id": f"movie:{m.id}",
                    "movie_id": m.id,
                    "tmdb_id": m.tmdb_id,
                    "title": m.title,
                    "year": m.year,
                    "genres": genres,
                    "directors": directors,
                    "cast": cast,
                    "tagline": m.tagline,
                    "keywords": m.keywords,
                    "collection_name": m.collection_name,
                    "poster_url": m.poster_url,
                    "letterboxd_uri": m.letterboxd_uri,
                    "text": text,
                }

                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Wrote {count} movies to {out_path}"))