FROM node:22-alpine

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy application source code
COPY src/ ./src/
# Ensure the uploads directory exists for file uploads
RUN mkdir -p uploads

# Expose server port
EXPOSE 5000

# Set production environment
ENV NODE_ENV=production

# Start application
CMD ["npm", "start"]
