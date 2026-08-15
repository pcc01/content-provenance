# Strapi has no official ready-to-run Docker Hub image, and the best-known
# community replacement (naskio/strapi) turned out to be broken — "Cannot
# find module 'react'" during its internal build step, reproduced against
# several tags while building this integration. This Dockerfile instead
# generates a real Strapi project at BUILD time via `create-strapi-app`,
# the same CLI Strapi's own docs point to — verified end-to-end (admin
# registration, content-type creation, API token, entry push/pull) against
# a real 5.52.0 instance produced by this exact command.
#
# The generated project is baked into the image so `docker-compose
# --profile cms up` boots immediately instead of re-running `npm install`
# on every container start; docker-compose.yml volume-mounts /opt/app so
# the admin account / content-types / sqlite data persist across restarts
# (Docker copies this image's /opt/app content into the volume on its
# first use — standard named-volume behavior, not something this
# Dockerfile has to arrange itself).
FROM node:20-bookworm-slim

WORKDIR /opt
RUN npx --yes create-strapi-app@latest app \
      --js --no-run --use-npm --install \
      --dbclient=sqlite --dbfile=.tmp/data.db \
      --no-example --no-git-init --skip-cloud --non-interactive

WORKDIR /opt/app
EXPOSE 1337
CMD ["npm", "run", "develop"]
