#FROM quay.io/pypa/manylinux2014_x86_64:latest
#RUN yum install -y openblas-devel.x86_64
#
FROM quay.io/pypa/manylinux2010_x86_64:2022-08-05-4535177

# libquadmath from devtoolset-8-libquadmath-devel.x86_64 was not built with -fPIC.
# Remove libquadmath-devel and restore the system default libquadmath.so
RUN yum remove -y devtoolset-8-libquadmath-devel.x86_64 && \
    yum install -y libquadmath.x86_64 && \
    ln -fs libquadmath.so.0 /usr/lib64/libquadmath.so

RUN yum install -y openblas-devel.x86_64 gcc && \
    yum clean all && \
    rm -rf /var/cache/yum

RUN /opt/_internal/tools/bin/pip3 install --no-cache-dir cmake

COPY build-wheels.sh /build-wheels.sh
CMD ['/build-wheels.sh']

# # openblas in quay.io/pypa/manylinux1_x86_64 has a bug that causes segfault
# # (issue https://github.com/pyscf/pyscf/issues/1095). openblas r0-3.3 fixed
# # the bug
# COPY --from 0 /usr/lib64/libopenblas.so /usr/lib64/libopenblas.so.0
# RUN rm -f libopenblas-r0.2.18.so && \
#     ln -fs /usr/lib64/libopenblas.so.0 /usr/lib64/libopenblas.so
