FROM nginx:alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY . /usr/share/nginx/html
RUN mkdir -p /var/cache/nginx/client_temp && chown -R nginx:nginx /var/cache/nginx
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
