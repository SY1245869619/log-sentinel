pipeline {
    agent any

    environment {
        DEPLOY_DIR = '/opt/logsentinel'
        COMPOSE_PROJECT_NAME = 'logsentinel'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                echo "代码检出完成"
                echo "工作目录: ${env.WORKSPACE}"
                sh 'pwd && ls -la'
            }
        }

        stage('Build Docker Images') {
            steps {
                script {
                    dir("${env.WORKSPACE}") {
                        // 构建 backend 与 web 两个镜像（镜像名在 compose 中固定）
                        sh 'docker compose build'
                        echo "Docker 镜像构建完成"
                    }
                }
            }
        }

        stage('Deploy') {
            steps {
                script {
                    // 1. 创建部署目录（数据持久化目录，不存在时自动创建）
                    sh "mkdir -p ${DEPLOY_DIR}/data/mysql ${DEPLOY_DIR}/data/redis ${DEPLOY_DIR}/logs"

                    // 2. 同步部署所需文件到部署目录
                    sh "cp ${env.WORKSPACE}/docker-compose.yml ${DEPLOY_DIR}/docker-compose.yml"
                    sh "mkdir -p ${DEPLOY_DIR}/sql && cp ${env.WORKSPACE}/sql/init.sql ${DEPLOY_DIR}/sql/init.sql"

                    // 3. 首次部署自动生成 .env（含随机密钥），已存在则保留
                    sh """
                        if [ ! -f ${DEPLOY_DIR}/.env ]; then
                            echo '首次部署，生成 .env（随机密钥）'
                            {
                                echo "MYSQL_ROOT_PASSWORD=\$(openssl rand -hex 16)"
                                echo "MYSQL_DATABASE=logsentinel"
                                echo "JWT_SECRET=\$(openssl rand -hex 32)"
                                echo "AES_KEY=\$(openssl rand -hex 16)"
                                echo "ADMIN_INITIAL_PASSWORD=Admin@123"
                                echo "WEB_PORT=6064"
                                echo "LOG_ROOT=/var/log"
                            } > ${DEPLOY_DIR}/.env
                        else
                            echo '.env 已存在，跳过生成'
                        fi
                    """

                    // 4. 停止旧容器并启动新容器（镜像已在上一步构建好）
                    sh """
                        cd ${DEPLOY_DIR}
                        docker compose down || true
                        docker compose up -d
                    """
                }
            }
        }

        stage('Health Check') {
            steps {
                script {
                    echo "等待容器启动..."
                    sleep(time: 40, unit: 'SECONDS')
                    def healthStatus = sh(
                        script: "docker inspect --format='{{.State.Health.Status}}' logsentinel-backend || echo 'unknown'",
                        returnStdout: true
                    ).trim()

                    if (healthStatus == 'healthy') {
                        echo "✅ 健康检查通过"
                    } else {
                        echo "❌ 健康检查失败，状态: ${healthStatus}"
                        sh 'docker logs logsentinel-backend --tail 100 || true'
                        error("部署失败")
                    }
                }
            }
        }
    }

    post {
        always {
            cleanWs()
        }
        failure {
            echo "❌ 构建失败，请查看控制台日志"
        }
        success {
            echo "✅ 构建并部署成功，访问 http://10.99.99.152:6064"
        }
    }
}
