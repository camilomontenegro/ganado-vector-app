#Use Node.js for Astro build
FROM node:20-alpine AS build

WORKDIR /app


COPY frontend/package.json . 
COPY frontend/. . 

RUN ls -al /app
RUN npm install

COPY . .
RUN npm run build

#Serve with a lightweight web server
FROM node:20-alpine

WORKDIR /app

RUN npm install -g serve

COPY --from=build /app/dist ./dist

EXPOSE 4321

CMD ["serve", "-s", "dist", "-l", "4321"]