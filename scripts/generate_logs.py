import time

def create_logs():
    # 1. Simulate Locust CSV (The Trigger)
    # This file tells the AI *when* the error happened (timestamp 1716300020)
    csv_content = """Timestamp,UserCount,Type,Name,Requests,Failures,MedianResponseTime,AverageResponseTime,MinResponseTime,MaxResponseTime,AverageContentSize,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%
1716300000,10,POST,/owners/new,50,0,12,15,5,105,450,5.5,0.0,12,15,18,20,25,30,45,55,80,95,105
1716300010,12,POST,/owners/new,50,0,13,16,6,110,452,5.2,0.0,12,15,18,20,25,30,45,55,80,95,105
1716300020,15,POST,/owners/new,50,5,500,850,200,2500,455,4.8,0.5,400,600,800,900,1200,1500,2000,2200,2400,2500,2500
"""
    
    with open("locust_stats.csv", "w") as f:
        f.write(csv_content)
    print("Created locust_stats.csv (Simulating failure at 1716300020)")

    # 2. Simulate Application Logs (The Evidence)
    # We inject a stack trace that points to OwnerController.java:105
    log_content = """
2024-05-21 14:00:15.123  INFO 1 --- [nio-8080-exec-1] o.s.web.servlet.DispatcherServlet        : Completed initialization in 5 ms
2024-05-21 14:00:18.456  INFO 1 --- [nio-8080-exec-3] o.s.s.petclinic.owner.OwnerController    : Processing new owner form
2024-05-21 14:00:20.001 ERROR 1 --- [nio-8080-exec-5] o.a.c.c.C.[.[.[/].[dispatcherServlet]    : Servlet.service() for servlet [dispatcherServlet] in context with path [] threw exception [Request processing failed; nested exception is java.lang.NullPointerException] with root cause

java.lang.NullPointerException: null
	at org.springframework.samples.petclinic.owner.OwnerController.processCreationForm(OwnerController.java:105) ~[classes/:na]
	at jdk.internal.reflect.NativeMethodAccessorImpl.invoke0(Native Method) ~[na:na]
	at jdk.internal.reflect.NativeMethodAccessorImpl.invoke(NativeMethodAccessorImpl.java:77) ~[na:na]
	at org.springframework.web.method.support.InvocableHandlerMethod.doInvoke(InvocableHandlerMethod.java:205) ~[spring-web-6.1.6.jar:6.1.6]
	at org.springframework.web.servlet.mvc.method.annotation.ServletInvocableHandlerMethod.invokeAndHandle(ServletInvocableHandlerMethod.java:118) ~[spring-webmvc-6.1.6.jar:6.1.6]
"""
    with open("petclinic_app.log", "w") as f:
        f.write(log_content)
    print("Created petclinic_app.log (Containing the simulated error)")

if __name__ == "__main__":
    create_logs()