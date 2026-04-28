FROM nginx:alpine

COPY nginx.conf /etc/nginx/nginx.conf:ro
COPY ssl/server.crt /etc/nginx/ssl/server.crt:ro
COPY ssl/server.key /etc/nginx/ssl/server.key:ro

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
