FROM nginx:alpine

RUN mkdir -p /etc/nginx/ssl

COPY nginx.conf /etc/nginx/nginx.conf
COPY ssl/server.crt /etc/nginx/ssl/server.crt
COPY ssl/server.key /etc/nginx/ssl/server.key

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
