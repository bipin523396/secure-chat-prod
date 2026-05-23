FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
COPY src ./src
RUN mvn -q package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/server-java-1.0-SNAPSHOT.jar app.jar
ENV PORT=5001
EXPOSE 5001
CMD ["sh", "-c", "java -jar app.jar"]
