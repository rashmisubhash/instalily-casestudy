import React from 'react'
import { Container, Row, Col } from 'react-bootstrap'
import { MessageSquare } from 'lucide-react'

export default function Header() {
  return (
    <header className="ps-header">
      <Container>
        <Row className="align-items-center">
          <Col md={6}>
            <div className="d-flex align-items-center">
              <MessageSquare size={32} color="#2f7879" className="me-2" />
              <h1 className="h4 mb-0" style={{ color: '#2f7879' }}>
                PartSelect Customer Support
              </h1>
            </div>
          </Col>
          <Col md={6} className="text-md-end mt-3 mt-md-0">
            <a href="tel:1-866-319-8402" className="ps-phone">
              1-866-319-8402
            </a>
            <p className="ps-phone-hours mb-0">Monday to Saturday</p>
            <p className="ps-phone-hours">8am - 8pm EST</p>
          </Col>
        </Row>
      </Container>
    </header>
  )
}