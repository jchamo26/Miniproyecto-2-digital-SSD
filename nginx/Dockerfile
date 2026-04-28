FROM nginx:alpine

COPY nginx.conf /etc/nginx/nginx.conf:ro

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
