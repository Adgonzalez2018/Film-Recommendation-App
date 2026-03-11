#!/usr/bin/env bash
set -euo pipefail

echo "Running small TMDB seed test..."

python manage.py seed_tmdb --source popular --pages 1 --stop-after 10 --skip-existing

echo ""
echo "Checking DB counts..."

python manage.py shell -c "
from api.models import Movie, Genre, Person, MovieGenre, MovieCast, MovieCrew
print('movies:', Movie.objects.count())
print('movies with tmdb_id:', Movie.objects.filter(tmdb_id__isnull=False).count())
print('movies with runtime:', Movie.objects.filter(runtime__isnull=False).count())
print('genres:', Genre.objects.count())
print('people:', Person.objects.count())
print('movie genres:', MovieGenre.objects.count())
print('movie cast:', MovieCast.objects.count())
print('movie crew:', MovieCrew.objects.count())
"